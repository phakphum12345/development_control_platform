"""Static contract checks for the same-origin OIDC ingress template."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
NGINX = ROOT / "deploy" / "oidc-edge" / "nginx.conf"


class OIDCIngressContractTests(unittest.TestCase):
    def test_nginx_template_keeps_signer_private_and_protects_dashboard_and_api(self):
        config = NGINX.read_text(encoding="utf-8")
        self.assertIn("location = /_dcp_auth", config)
        self.assertIn("internal;", config)
        self.assertIn("127.0.0.1:8790", config)
        self.assertIn("proxy_pass http://dcp_identity_signer/authorize;", config)
        self.assertIn("auth_request /_dcp_auth;", config)
        self.assertIn("location ^~ /oauth2/", config)
        self.assertIn("auth_request off;", config)
        self.assertIn("location ^~ /api/", config)
        self.assertIn("location / {", config)

    def test_every_dcp_identity_header_is_overwritten_from_signer(self):
        config = NGINX.read_text(encoding="utf-8")
        for name, variable in (
            ("X-DCP-User", "$dcp_user"),
            ("X-DCP-Role", "$dcp_role"),
            ("X-DCP-Session", "$dcp_session"),
            ("X-DCP-Auth-Timestamp", "$dcp_timestamp"),
            ("X-DCP-Auth-Nonce", "$dcp_nonce"),
            ("X-DCP-Auth-Signature", "$dcp_signature"),
        ):
            with self.subTest(header=name):
                self.assertIn(f"proxy_set_header {name} {variable};", config)
        self.assertIn('proxy_set_header Cookie "";', config)
        self.assertIn('proxy_set_header Authorization "";', config)

    def test_same_origin_csrf_and_origin_are_forwarded_to_gateway(self):
        config = NGINX.read_text(encoding="utf-8")
        self.assertIn("proxy_set_header Origin $http_origin;", config)
        self.assertIn("proxy_set_header X-CSRF-Token $http_x_csrf_token;", config)
        self.assertIn("proxy_set_header Idempotency-Key $http_idempotency_key;", config)
        self.assertIn("proxy_set_header X-Forwarded-Proto https;", config)
        self.assertIn("error_page 401 = @api_unauthorized;", config)
        self.assertIn("error_page 401 = /oauth2/start;", config)
        self.assertIn("proxy_set_header X-Auth-Request-Redirect https://$host$request_uri;", config)
        self.assertIn('add_header Cache-Control "no-store" always;', config)


if __name__ == "__main__":
    unittest.main()
