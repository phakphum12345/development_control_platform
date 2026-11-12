"""Tests for read-only Azure Firewall egress verification."""
import json
import unittest
from urllib.error import URLError
from urllib.parse import urlparse

from tools.cloud_gateway.azure_egress import (
    AzureEgressPolicyError,
    AzureEgressPolicyVerifier,
    GitHubActionsDomainCatalog,
)


SUBSCRIPTION = "00000000-0000-0000-0000-000000000000"
COMPUTE_RG = "dcp-runners"
NETWORK_RG = "dcp-network"
PREFIX = "10.0.2.0/24"
FIREWALL_IP = "10.0.0.4"
DOMAINS = ("github.com", "api.github.com", "*.actions.githubusercontent.com")


def rid(kind, name, rg=NETWORK_RG):
    return (
        f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{rg}"
        f"/providers/Microsoft.Network/{kind}/{name}"
    )


SUBNET = rid("virtualNetworks", "vnet1") + "/subnets/runners"
VNET = rid("virtualNetworks", "vnet1")
NSG = rid("networkSecurityGroups", "runner-nsg")
ROUTE_TABLE = rid("routeTables", "runner-rt")
FIREWALL = rid("azureFirewalls", "runner-fw")
POLICY = rid("firewallPolicies", "runner-policy")


class FakeArm:
    subscription_id = SUBSCRIPTION
    resource_group = COMPUTE_RG

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def request(self, method, url):
        self.calls.append((method, url))
        path = urlparse(url).path
        if path not in self.responses:
            raise AssertionError("Unexpected ARM request: " + path)
        return self.responses[path]


def base_responses(domains=DOMAINS):
    return {
        SUBNET: {
            "properties": {
                "provisioningState": "Succeeded",
                "networkSecurityGroup": {"id": NSG},
                "routeTable": {"id": ROUTE_TABLE},
                "addressPrefix": PREFIX,
            }
        },
        NSG: {
            "properties": {
                "provisioningState": "Succeeded",
                "securityRules": [{
                    "properties": {
                        "direction": "Inbound",
                        "access": "Deny",
                        "priority": 1000,
                        "protocol": "*",
                        "sourceAddressPrefix": "*",
                        "destinationAddressPrefix": "*",
                        "sourcePortRange": "*",
                        "destinationPortRange": "*",
                    }
                }],
            }
        },
        ROUTE_TABLE: {
            "properties": {
                "provisioningState": "Succeeded",
                "disableBgpRoutePropagation": True,
                "routes": [
                    {"properties": {
                        "addressPrefix": "0.0.0.0/0",
                        "nextHopType": "VirtualAppliance",
                        "nextHopIpAddress": FIREWALL_IP,
                    }},
                    {"properties": {
                        "addressPrefix": "10.0.0.0/16",
                        "nextHopType": "VnetLocal",
                    }},
                ],
            }
        },
        FIREWALL: {
            "properties": {
                "provisioningState": "Succeeded",
                "firewallPolicy": {"id": POLICY},
                "ipConfigurations": [
                    {"properties": {"privateIPAddress": FIREWALL_IP}}
                ],
            }
        },
        VNET: {
            "properties": {
                "provisioningState": "Succeeded",
                "dhcpOptions": {"dnsServers": [FIREWALL_IP]},
            }
        },
        POLICY: {
            "properties": {
                "provisioningState": "Succeeded",
                "dnsSettings": {"enableProxy": True},
            }
        },
        POLICY + "/ruleCollectionGroups": {
            "value": [{
                "properties": {
                    "provisioningState": "Succeeded",
                    "ruleCollections": [{
                        "ruleCollectionType": "FirewallPolicyFilterRuleCollection",
                        "action": {"type": "Allow"},
                        "rules": [{
                            "ruleType": "ApplicationRule",
                            "protocols": [{"protocolType": "Https", "port": 443}],
                            "sourceAddresses": [PREFIX],
                            "targetFqdns": list(domains),
                        }],
                    }],
                }
            }]
        },
    }


def verifier(responses=None, **kwargs):
    return AzureEgressPolicyVerifier(
        FakeArm(responses or base_responses()),
        route_table_id=ROUTE_TABLE,
        firewall_id=FIREWALL,
        firewall_policy_id=POLICY,
        domain_catalog=lambda: DOMAINS,
        **kwargs,
    )


class AzureEgressPolicyVerifierTests(unittest.TestCase):
    def test_accepts_exact_github_actions_https_egress_through_firewall(self):
        instance = verifier()
        self.assertTrue(instance.verify("linux", SUBNET, NSG))
        self.assertTrue(instance("windows", SUBNET, NSG))

    def test_rejects_wrong_subnet_nsg_or_route_table_association(self):
        for key, value in (
            ("networkSecurityGroup", {"id": rid("networkSecurityGroups", "other")}),
            ("routeTable", {"id": rid("routeTables", "other")}),
        ):
            responses = base_responses()
            responses[SUBNET]["properties"][key] = value
            with self.subTest(key=key), self.assertRaises(AzureEgressPolicyError):
                verifier(responses).verify("linux", SUBNET, NSG)

    def test_rejects_missing_firewall_default_route_or_bgp_propagation(self):
        responses = base_responses()
        responses[ROUTE_TABLE]["properties"]["routes"][0]["properties"]["nextHopType"] = "Internet"
        with self.assertRaises(AzureEgressPolicyError):
            verifier(responses).verify("linux", SUBNET, NSG)
        responses = base_responses()
        responses[ROUTE_TABLE]["properties"]["disableBgpRoutePropagation"] = False
        with self.assertRaises(AzureEgressPolicyError):
            verifier(responses).verify("linux", SUBNET, NSG)

    def test_rejects_dns_proxy_disabled_or_vnet_dns_bypass(self):
        responses = base_responses()
        responses[POLICY]["properties"]["dnsSettings"]["enableProxy"] = False
        with self.assertRaises(AzureEgressPolicyError):
            verifier(responses).verify("linux", SUBNET, NSG)
        responses = base_responses()
        responses[VNET]["properties"]["dhcpOptions"]["dnsServers"] = ["8.8.8.8"]
        with self.assertRaises(AzureEgressPolicyError):
            verifier(responses).verify("linux", SUBNET, NSG)


    def test_rejects_unapproved_custom_dns_upstream(self):
        responses = base_responses()
        responses[POLICY]["properties"]["dnsSettings"]["servers"] = ["10.0.0.53"]
        with self.assertRaises(AzureEgressPolicyError):
            verifier(responses).verify("linux", SUBNET, NSG)

    def test_rejects_custom_inbound_allow_rules(self):
        responses = base_responses()
        responses[NSG]["properties"]["securityRules"] = [{
            "properties": {"direction": "Inbound", "access": "Allow"}
        }]
        with self.assertRaises(AzureEgressPolicyError):
            verifier(responses).verify("linux", SUBNET, NSG)


    def test_rejects_nsg_without_a_custom_deny_all_override(self):
        responses = base_responses()
        responses[NSG]["properties"]["securityRules"] = []
        with self.assertRaises(AzureEgressPolicyError):
            verifier(responses).verify("linux", SUBNET, NSG)
        responses = base_responses()
        responses[NSG]["properties"]["securityRules"][0]["properties"]["destinationPortRange"] = "22"
        with self.assertRaises(AzureEgressPolicyError):
            verifier(responses).verify("linux", SUBNET, NSG)

    def test_rejects_broad_or_non_https_firewall_allow_rules(self):
        responses = base_responses()
        rule = responses[POLICY + "/ruleCollectionGroups"]["value"][0]["properties"]["ruleCollections"][0]["rules"][0]
        rule["targetFqdns"].append("*.com")
        with self.assertRaises(AzureEgressPolicyError):
            verifier(responses).verify("linux", SUBNET, NSG)
        responses = base_responses()
        rule = responses[POLICY + "/ruleCollectionGroups"]["value"][0]["properties"]["ruleCollections"][0]["rules"][0]
        rule["protocols"] = [{"protocolType": "Tcp", "port": 443}]
        with self.assertRaises(AzureEgressPolicyError):
            verifier(responses).verify("linux", SUBNET, NSG)

    def test_rejects_network_allow_rules_and_inherited_policy(self):
        responses = base_responses()
        rule = responses[POLICY + "/ruleCollectionGroups"]["value"][0]["properties"]["ruleCollections"][0]["rules"][0]
        rule["ruleType"] = "NetworkRule"
        with self.assertRaises(AzureEgressPolicyError):
            verifier(responses).verify("linux", SUBNET, NSG)
        responses = base_responses()
        responses[POLICY]["properties"]["basePolicy"] = {"id": rid("firewallPolicies", "parent")}
        with self.assertRaises(AzureEgressPolicyError):
            verifier(responses).verify("linux", SUBNET, NSG)

    def test_rejects_source_scope_wildcard_and_fqdn_catalog_mismatch(self):
        responses = base_responses()
        rule = responses[POLICY + "/ruleCollectionGroups"]["value"][0]["properties"]["ruleCollections"][0]["rules"][0]
        rule["sourceAddresses"] = ["*"]
        with self.assertRaises(AzureEgressPolicyError):
            verifier(responses).verify("linux", SUBNET, NSG)
        responses = base_responses()
        rule = responses[POLICY + "/ruleCollectionGroups"]["value"][0]["properties"]["ruleCollections"][0]["rules"][0]
        rule["targetFqdns"].remove("api.github.com")
        with self.assertRaises(AzureEgressPolicyError):
            verifier(responses).verify("linux", SUBNET, NSG)


    def test_rejects_explicit_deny_and_nat_collections_in_dedicated_policy(self):
        responses = base_responses()
        collection = responses[POLICY + "/ruleCollectionGroups"]["value"][0]["properties"]["ruleCollections"][0]
        collection["action"] = {"type": "Deny"}
        with self.assertRaises(AzureEgressPolicyError):
            verifier(responses).verify("linux", SUBNET, NSG)
        responses = base_responses()
        collection = responses[POLICY + "/ruleCollectionGroups"]["value"][0]["properties"]["ruleCollections"][0]
        collection["ruleCollectionType"] = "FirewallPolicyNatRuleCollection"
        with self.assertRaises(AzureEgressPolicyError):
            verifier(responses).verify("linux", SUBNET, NSG)

    def test_accepts_only_explicit_operator_extra_fqdns(self):
        extra = "packages.example.test"
        responses = base_responses(DOMAINS + (extra,))
        instance = verifier(responses, extra_fqdns=(extra,))
        self.assertTrue(instance.verify("linux", SUBNET, NSG))
        with self.assertRaises(ValueError):
            verifier(extra_fqdns=("*.com",))

    def test_rejects_network_controls_in_runner_resource_group_and_nonprivate_subnet(self):
        with self.assertRaises(ValueError):
            AzureEgressPolicyVerifier(
                FakeArm(base_responses()),
                route_table_id=rid("routeTables", "rt", COMPUTE_RG),
                firewall_id=FIREWALL,
                firewall_policy_id=POLICY,
                domain_catalog=lambda: DOMAINS,
            )
        responses = base_responses()
        responses[SUBNET]["properties"]["addressPrefix"] = "8.8.8.0/24"
        with self.assertRaises(AzureEgressPolicyError):
            verifier(responses).verify("linux", SUBNET, NSG)


    def test_builds_verifier_from_environment_without_echoing_configuration(self):
        env = {
            "DCP_AZURE_ROUTE_TABLE_ID": ROUTE_TABLE,
            "DCP_AZURE_FIREWALL_ID": FIREWALL,
            "DCP_AZURE_FIREWALL_POLICY_ID": POLICY,
            "DCP_AZURE_EGRESS_EXTRA_FQDNS": "packages.example.test",
        }
        instance = AzureEgressPolicyVerifier.from_environment(
            FakeArm(base_responses(DOMAINS + ("packages.example.test",))),
            env,
            domain_catalog=lambda: DOMAINS,
        )
        self.assertEqual(instance.extra_fqdns, ("packages.example.test",))
        self.assertTrue(instance.verify("linux", SUBNET, NSG))

    def test_unknown_os_fails_closed(self):
        with self.assertRaises(AzureEgressPolicyError):
            verifier().verify("macos", SUBNET, NSG)

    def test_callable_returns_false_on_any_unknown_or_unavailable_condition(self):
        responses = base_responses()
        responses[POLICY]["properties"]["dnsSettings"]["enableProxy"] = False
        instance = verifier(responses)
        self.assertFalse(instance("linux", SUBNET, NSG))
        self.assertIn("DNS proxy", instance.last_error)


class FakeCatalogResponse:
    status = 200

    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, limit):
        return self.body[:limit]


class FakeCatalogOpener:
    def __init__(self, body):
        self.body = body
        self.calls = 0

    def __call__(self, request, timeout):
        self.calls += 1
        return FakeCatalogResponse(self.body)


class GitHubActionsDomainCatalogTests(unittest.TestCase):
    def test_fetches_and_caches_official_actions_domain_list(self):
        body = json.dumps({"domains": {"actions": list(DOMAINS)}}).encode()
        opener = FakeCatalogOpener(body)
        clock = [1000]
        catalog = GitHubActionsDomainCatalog(opener=opener, clock=lambda: clock[0])
        self.assertEqual(set(catalog()), set(DOMAINS))
        self.assertEqual(set(catalog()), set(DOMAINS))
        self.assertEqual(opener.calls, 1)
        clock[0] += 3601
        catalog()
        self.assertEqual(opener.calls, 2)

    def test_rejects_invalid_or_unavailable_catalog(self):
        bad = FakeCatalogOpener(b'{"domains":{"actions":["*"]}}')
        with self.assertRaises(AzureEgressPolicyError):
            GitHubActionsDomainCatalog(opener=bad)()
        class Offline:
            def __call__(self, request, timeout):
                raise URLError("offline")
        with self.assertRaises(AzureEgressPolicyError):
            GitHubActionsDomainCatalog(opener=Offline())()


if __name__ == "__main__":
    unittest.main()
