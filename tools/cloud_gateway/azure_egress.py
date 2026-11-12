"""Read-only Azure Firewall egress verifier for ephemeral GitHub Actions runners.

The verifier proves the runner subnet is attached to the expected NSG and UDR,
that the UDR sends the default route to the expected Azure Firewall, that the
firewall's policy enables DNS proxy, and that the policy allows only the
current GitHub Actions FQDN catalog (plus explicit operator additions) over
HTTPS/443 from the runner subnet. It never creates or changes Azure resources.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


API_NETWORK = "2025-05-01"
API_FIREWALL = "2025-09-01"
API_POLICY = "2025-09-01"
ARM_ROOT = "https://management.azure.com"
GITHUB_META_URL = "https://api.github.com/meta"


class AzureEgressPolicyError(RuntimeError):
    """Azure network resources do not prove the required restricted egress."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _valid_fqdn_pattern(value: str) -> bool:
    if not isinstance(value, str) or not value or len(value) > 253:
        return False
    domain = value[2:] if value.startswith("*.") else value
    if "*" in domain or domain.startswith(".") or domain.endswith(".") or ".." in domain:
        return False
    labels = domain.split(".")
    if len(labels) < 2:
        return False
    return all(
        1 <= len(label) <= 63
        and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label)
        for label in labels
    )


class GitHubActionsDomainCatalog:
    """Fetch and briefly cache GitHub's official Actions egress FQDN catalog."""

    def __init__(self, timeout=5.0, ttl=3600, opener=None, clock=None):
        if not 1 <= timeout <= 10 or not 60 <= ttl <= 3600:
            raise ValueError("Invalid GitHub Actions domain catalog timeout or TTL")
        self.timeout = float(timeout)
        self.ttl = int(ttl)
        self.opener = opener or build_opener(_NoRedirect()).open
        self.clock = clock or time.time
        self._cached = None
        self._cached_at = 0

    def __call__(self):
        now = int(self.clock())
        if self._cached is not None and now - self._cached_at < self.ttl:
            return self._cached
        request = Request(
            GITHUB_META_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "DCP-Azure-Egress-Preflight/1.0",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            method="GET",
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                status = getattr(response, "status", None)
                if status is None:
                    status = response.getcode()
                if status != 200:
                    raise AzureEgressPolicyError("GitHub egress catalog returned a non-200 response")
                raw = response.read(1048577)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise AzureEgressPolicyError("GitHub egress catalog is unavailable") from exc
        if len(raw) > 1048576:
            raise AzureEgressPolicyError("GitHub egress catalog exceeded the size limit")
        try:
            data = json.loads(raw.decode("utf-8"))
            domains = data["domains"]["actions"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise AzureEgressPolicyError("GitHub egress catalog has an invalid response shape") from exc
        if not isinstance(domains, list) or not 1 <= len(domains) <= 512:
            raise AzureEgressPolicyError("GitHub egress catalog is empty or too large")
        normalized = set()
        for domain in domains:
            if not _valid_fqdn_pattern(domain):
                raise AzureEgressPolicyError("GitHub egress catalog contains an invalid FQDN pattern")
            normalized.add(domain.lower())
        self._cached = tuple(sorted(normalized))
        self._cached_at = now
        return self._cached


class AzureEgressPolicyVerifier:
    """Verify the read-only Azure Firewall path and exact allowed FQDN policy."""

    def __init__(
        self,
        arm,
        *,
        route_table_id: str,
        firewall_id: str,
        firewall_policy_id: str,
        domain_catalog=None,
        extra_fqdns=(),
    ):
        self.arm = arm
        self.last_error = None
        self.route_table_id = route_table_id
        self.firewall_id = firewall_id
        self.firewall_policy_id = firewall_policy_id
        self.domain_catalog = domain_catalog or GitHubActionsDomainCatalog()
        self.extra_fqdns = tuple(item.strip().lower() for item in extra_fqdns if isinstance(item, str) and item.strip())
        for domain in self.extra_fqdns:
            if not _valid_fqdn_pattern(domain):
                raise ValueError("Invalid explicit additional runner egress FQDN")
        if len(set(self.extra_fqdns)) != len(self.extra_fqdns):
            raise ValueError("Duplicate additional runner egress FQDN")

        self._validate_network_resource_id(route_table_id, "routeTables")
        self._validate_network_resource_id(firewall_id, "azureFirewalls")
        self._validate_network_resource_id(firewall_policy_id, "firewallPolicies")

    @classmethod
    def from_environment(cls, arm, env=None, domain_catalog=None):
        values = os.environ if env is None else env
        extras = tuple(
            item.strip() for item in values.get("DCP_AZURE_EGRESS_EXTRA_FQDNS", "").split(",")
            if item.strip()
        )
        return cls(
            arm,
            route_table_id=values.get("DCP_AZURE_ROUTE_TABLE_ID", ""),
            firewall_id=values.get("DCP_AZURE_FIREWALL_ID", ""),
            firewall_policy_id=values.get("DCP_AZURE_FIREWALL_POLICY_ID", ""),
            domain_catalog=domain_catalog,
            extra_fqdns=extras,
        )

    def _validate_network_resource_id(self, value, resource_type):
        subscription = re.escape(self.arm.subscription_id)
        pattern = (
            r"^/subscriptions/" + subscription
            + r"/resourceGroups/[A-Za-z0-9_.()-]{1,90}/providers/Microsoft\.Network/"
            + re.escape(resource_type) + r"/[A-Za-z0-9_.()-]{1,90}$"
        )
        if not isinstance(value, str) or not re.fullmatch(pattern, value, re.I):
            raise ValueError("Invalid Azure network resource ID: " + resource_type)
        rg = re.search(r"/resourceGroups/([^/]+)/", value, re.I).group(1)
        if rg.lower() == self.arm.resource_group.lower():
            raise ValueError("Network controls must be in a separate resource group from ephemeral runners")

    @staticmethod
    def _state(data, label):
        state = data.get("properties", {}).get("provisioningState")
        if not isinstance(state, str) or state.lower() != "succeeded":
            raise AzureEgressPolicyError(label + " is not in Succeeded provisioning state")

    @staticmethod
    def _same_id(actual, expected):
        return isinstance(actual, str) and actual.rstrip("/").lower() == expected.rstrip("/").lower()

    def _get(self, resource_id, api_version):
        return self.arm.request(
            "GET", ARM_ROOT + resource_id + "?api-version=" + api_version
        )

    @staticmethod
    def _subnet_prefixes(properties):
        raw = properties.get("addressPrefixes")
        if not raw:
            single = properties.get("addressPrefix")
            raw = [single] if single else []
        if not isinstance(raw, list) or not 1 <= len(raw) <= 16:
            raise AzureEgressPolicyError("Runner subnet address prefixes are missing")
        prefixes = set()
        for value in raw:
            try:
                network = ipaddress.ip_network(value, strict=True)
            except (TypeError, ValueError) as exc:
                raise AzureEgressPolicyError("Runner subnet address prefix is invalid") from exc
            if not isinstance(network, ipaddress.IPv4Network) or not network.is_private:
                raise AzureEgressPolicyError("Runner subnet must use private IPv4 address space")
            prefixes.add(str(network))
        return tuple(sorted(prefixes))

    def _check_route_table(self, route_table, firewall_ip):
        self._state(route_table, "Azure route table")
        properties = route_table.get("properties", {})
        if properties.get("disableBgpRoutePropagation") is not True:
            raise AzureEgressPolicyError("Runner route table must disable BGP route propagation")
        routes = properties.get("routes")
        if not isinstance(routes, list):
            raise AzureEgressPolicyError("Runner route table has no route list")
        default_routes = []
        for item in routes:
            rule = item.get("properties", {})
            prefix = rule.get("addressPrefix")
            next_hop = rule.get("nextHopType")
            if prefix == "0.0.0.0/0":
                default_routes.append(rule)
                continue
            if next_hop in ("Internet", "VirtualNetworkGateway", "None"):
                raise AzureEgressPolicyError("Runner route table contains a route that can bypass Azure Firewall")
            if next_hop == "VirtualAppliance" and rule.get("nextHopIpAddress") != firewall_ip:
                raise AzureEgressPolicyError("Runner route table contains a different virtual appliance next hop")
            if next_hop in ("VnetLocal", "VirtualNetwork"):
                try:
                    network = ipaddress.ip_network(prefix, strict=True)
                except (TypeError, ValueError) as exc:
                    raise AzureEgressPolicyError("Runner private route prefix is invalid") from exc
                if not network.is_private:
                    raise AzureEgressPolicyError("Runner route table contains a non-private local route")
            elif next_hop != "VirtualAppliance":
                raise AzureEgressPolicyError("Runner route table contains an unsupported next-hop type")
        if len(default_routes) != 1:
            raise AzureEgressPolicyError("Exactly one default route through Azure Firewall is required")
        default = default_routes[0]
        if default.get("nextHopType") != "VirtualAppliance" or default.get("nextHopIpAddress") != firewall_ip:
            raise AzureEgressPolicyError("Runner default route does not point to the configured Azure Firewall")

    def _check_firewall_policy_rules(self, policy_id, subnet_prefixes):
        url = ARM_ROOT + policy_id + "/ruleCollectionGroups?api-version=" + API_POLICY
        groups = []
        for _ in range(10):
            page = self.arm.request("GET", url)
            values = page.get("value")
            if not isinstance(values, list):
                raise AzureEgressPolicyError("Azure Firewall Policy rule collection list is invalid")
            groups.extend(values)
            next_link = page.get("nextLink")
            if not next_link:
                break
            parsed = urlparse(next_link)
            if (
                parsed.scheme != "https" or parsed.hostname != "management.azure.com"
                or parsed.username is not None or parsed.password is not None
                or parsed.port is not None or parsed.fragment
                or not parsed.path.lower().startswith((policy_id + "/rulecollectiongroups").lower())
            ):
                raise AzureEgressPolicyError("Azure Firewall Policy returned an untrusted pagination URL")
            url = next_link
        else:
            raise AzureEgressPolicyError("Azure Firewall Policy rule collection pagination exceeded the limit")
        if not groups:
            raise AzureEgressPolicyError("Azure Firewall Policy contains no rule collection groups")

        allowed_fqdns = set()
        allowed_rule_count = 0
        for group in groups:
            self._state(group, "Azure Firewall Policy rule collection group")
            collections = group.get("properties", {}).get("ruleCollections")
            if not isinstance(collections, list):
                raise AzureEgressPolicyError("Azure Firewall Policy rule collections are invalid")
            for collection in collections:
                collection_type = collection.get("ruleCollectionType")
                if collection_type == "FirewallPolicyNatRuleCollection":
                    raise AzureEgressPolicyError("Dedicated runner firewall policy must not contain NAT rules")
                action = collection.get("action", {}).get("type")
                if action == "Deny":
                    raise AzureEgressPolicyError("Dedicated runner policy must use implicit deny without explicit deny collections")
                if action != "Allow" or collection_type != "FirewallPolicyFilterRuleCollection":
                    raise AzureEgressPolicyError("Unsupported Azure Firewall allow rule collection")
                rules = collection.get("rules")
                if not isinstance(rules, list) or not rules:
                    raise AzureEgressPolicyError("Azure Firewall allow collection has no rules")
                for rule in rules:
                    if rule.get("ruleType") != "ApplicationRule":
                        raise AzureEgressPolicyError("Runner egress may use only HTTPS FQDN application rules")
                    if rule.get("targetUrls") or rule.get("fqdnTags") or rule.get("webCategories"):
                        raise AzureEgressPolicyError("Runner egress application rules must use explicit FQDNs only")
                    sources = rule.get("sourceAddresses")
                    if not isinstance(sources, list) or set(sources) != set(subnet_prefixes):
                        raise AzureEgressPolicyError("Runner egress rules must be scoped exactly to the runner subnet")
                    if rule.get("sourceIpGroups") or rule.get("sourceKubeSelectorGroups"):
                        raise AzureEgressPolicyError("Runner egress rules cannot use indirect source groups")
                    protocols = rule.get("protocols")
                    if (
                        not isinstance(protocols, list) or len(protocols) != 1
                        or protocols[0].get("protocolType") != "Https"
                        or protocols[0].get("port") != 443
                    ):
                        raise AzureEgressPolicyError("Runner egress rules must allow HTTPS on port 443 only")
                    targets = rule.get("targetFqdns")
                    if not isinstance(targets, list) or not targets:
                        raise AzureEgressPolicyError("Runner egress application rule has no FQDN targets")
                    for target in targets:
                        if not _valid_fqdn_pattern(target):
                            raise AzureEgressPolicyError("Runner egress rule contains an invalid FQDN pattern")
                        allowed_fqdns.add(target.lower())
                    allowed_rule_count += 1
        if allowed_rule_count == 0:
            raise AzureEgressPolicyError("Azure Firewall Policy has no approved runner application rules")
        return allowed_fqdns

    def verify(self, os_name: str, subnet_id: str, nsg_id: str):
        if os_name not in ("linux", "windows"):
            raise AzureEgressPolicyError("Azure restricted egress supports Linux and Windows only")
        # A subnet ID is nested below a virtual network; validate its full shape.
        subnet_pattern = (
            r"^/subscriptions/" + re.escape(self.arm.subscription_id)
            + r"/resourceGroups/[A-Za-z0-9_.()-]{1,90}/providers/Microsoft\.Network/"
            r"virtualNetworks/[A-Za-z0-9_.()-]{1,90}/subnets/[A-Za-z0-9_.()-]{1,90}$"
        )
        if not re.fullmatch(subnet_pattern, subnet_id, re.I):
            raise AzureEgressPolicyError("Invalid runner subnet resource ID")
        self._validate_network_resource_id(nsg_id, "networkSecurityGroups")
        for resource_id in (subnet_id, nsg_id):
            rg = re.search(r"/resourceGroups/([^/]+)/", resource_id, re.I).group(1)
            if rg.lower() == self.arm.resource_group.lower():
                raise AzureEgressPolicyError("Network controls must be outside the ephemeral runner resource group")

        subnet = self._get(subnet_id, API_NETWORK)
        self._state(subnet, "Runner subnet")
        subnet_props = subnet.get("properties", {})
        if not self._same_id(subnet_props.get("networkSecurityGroup", {}).get("id"), nsg_id):
            raise AzureEgressPolicyError("Runner subnet is not attached to the configured NSG")
        if not self._same_id(subnet_props.get("routeTable", {}).get("id"), self.route_table_id):
            raise AzureEgressPolicyError("Runner subnet is not attached to the configured route table")
        subnet_prefixes = self._subnet_prefixes(subnet_props)
        vnet_id = subnet_id.rsplit("/subnets/", 1)[0]

        nsg = self._get(nsg_id, API_NETWORK)
        self._state(nsg, "Runner NSG")
        nsg_rules = nsg.get("properties", {}).get("securityRules")
        if not isinstance(nsg_rules, list):
            raise AzureEgressPolicyError("Runner NSG security rules are invalid")
        for rule in nsg_rules:
            properties = rule.get("properties", {})
            if (
                str(properties.get("direction", "")).lower() == "inbound"
                and str(properties.get("access", "")).lower() == "allow"
            ):
                raise AzureEgressPolicyError("Runner NSG must not contain custom inbound allow rules")

        route_table = self._get(self.route_table_id, API_NETWORK)
        firewall = self._get(self.firewall_id, API_FIREWALL)
        self._state(firewall, "Azure Firewall")
        firewall_props = firewall.get("properties", {})
        if not self._same_id(firewall_props.get("firewallPolicy", {}).get("id"), self.firewall_policy_id):
            raise AzureEgressPolicyError("Azure Firewall is not attached to the configured policy")
        ip_configs = firewall_props.get("ipConfigurations")
        if not isinstance(ip_configs, list):
            raise AzureEgressPolicyError("Azure Firewall has no IP configurations")
        private_ips = {
            item.get("properties", {}).get("privateIPAddress")
            for item in ip_configs
            if item.get("properties", {}).get("privateIPAddress")
        }
        if len(private_ips) != 1:
            raise AzureEgressPolicyError("Azure Firewall must have exactly one verified private IP")
        firewall_ip = next(iter(private_ips))
        try:
            if not ipaddress.ip_address(firewall_ip).is_private:
                raise ValueError
        except ValueError as exc:
            raise AzureEgressPolicyError("Azure Firewall private IP is invalid") from exc
        self._check_route_table(route_table, firewall_ip)

        vnet = self._get(vnet_id, API_NETWORK)
        self._state(vnet, "Runner virtual network")
        dns_servers = vnet.get("properties", {}).get("dhcpOptions", {}).get("dnsServers")
        if dns_servers != [firewall_ip]:
            raise AzureEgressPolicyError("Runner VNet DNS must point only to the Azure Firewall DNS proxy")

        policy = self._get(self.firewall_policy_id, API_POLICY)
        self._state(policy, "Azure Firewall Policy")
        policy_props = policy.get("properties", {})
        if policy_props.get("basePolicy"):
            raise AzureEgressPolicyError("Inherited Azure Firewall policies are not accepted for runner egress")
        if policy_props.get("dnsSettings", {}).get("enableProxy") is not True:
            raise AzureEgressPolicyError("Azure Firewall Policy DNS proxy must be enabled")

        catalog = self.domain_catalog()
        if not isinstance(catalog, (list, tuple, set)) or not catalog:
            raise AzureEgressPolicyError("GitHub Actions FQDN catalog is empty")
        required_fqdns = set()
        for domain in (*catalog, *self.extra_fqdns):
            if not _valid_fqdn_pattern(domain):
                raise AzureEgressPolicyError("Required runner egress catalog contains an invalid FQDN")
            required_fqdns.add(domain.lower())
        if len(required_fqdns) > 512:
            raise AzureEgressPolicyError("Runner egress FQDN allowlist exceeds the configured limit")

        actual_fqdns = self._check_firewall_policy_rules(
            self.firewall_policy_id, subnet_prefixes
        )
        if actual_fqdns != required_fqdns:
            raise AzureEgressPolicyError("Azure Firewall allowlist does not exactly match the approved runner FQDN catalog")
        return True

    def __call__(self, os_name: str, subnet_id: str, nsg_id: str) -> bool:
        try:
            result = self.verify(os_name, subnet_id, nsg_id) is True
            self.last_error = None
            return result
        except AzureEgressPolicyError as exc:
            self.last_error = str(exc)[:240]
            return False
        except Exception:
            self.last_error = "Unexpected Azure egress verification failure"
            return False
