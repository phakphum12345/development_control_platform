import unittest
from unittest.mock import patch
from tools import dev_environment as dev


class DevEnvironmentTests(unittest.TestCase):
    def test_status_reports_missing_tools_as_unknown_not_pass(self):
        inventory = {"python": "/python", "flutter": None, "adb": None, "android_emulator": None,
                     "node": None, "npm": None, "vscode": None, "xcrun": None}
        with patch.object(dev, "_tool_inventory", return_value=inventory):
            result = dev.status()
        self.assertEqual(result["status"], "unknown")
        self.assertIn("flutter", result["missing_tools"])

    def test_avds_unknown_when_emulator_is_missing(self):
        with patch.object(dev, "_find_tool", return_value=None):
            result = dev.avds()
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["avds"], [])

    def test_launch_rejects_names_not_in_installed_list(self):
        with patch.object(dev, "avds", return_value={"status": "pass", "avds": ["Pixel_API_35"]}):
            result = dev.launch_avd("Other_AVD")
        self.assertEqual(result["status"], "fail")
        self.assertIn("available_avds", result)

    def test_launch_rejects_option_like_and_path_names(self):
        for name in ("-wipe-data", "../outside", "folder\\avd", ""):
            with self.subTest(name=name):
                self.assertEqual(dev.launch_avd(name)["status"], "fail")

    def test_launch_uses_argument_list_without_shell(self):
        with patch.object(dev, "avds", return_value={"status": "pass", "avds": ["Pixel_API_35"]}), \
             patch.object(dev, "_find_tool", return_value="/sdk/emulator"), \
             patch.object(dev.subprocess, "Popen") as popen:
            popen.return_value.pid = 123
            result = dev.launch_avd("Pixel_API_35")
        self.assertEqual(result["status"], "pass")
        popen.assert_called_once_with(["/sdk/emulator", "-avd", "Pixel_API_35"],
            stdin=dev.subprocess.DEVNULL, stdout=dev.subprocess.DEVNULL,
            stderr=dev.subprocess.DEVNULL, shell=False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
