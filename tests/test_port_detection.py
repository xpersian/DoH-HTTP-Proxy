import os
import types
import unittest
from unittest.mock import Mock, patch

import doh_http_proxy


class PortDetectionTests(unittest.TestCase):
    def test_parse_listening_rows_ignores_non_listening_entries(self) -> None:
        stdout = "\n".join(
            [
                "TCP    0.0.0.0:8080    0.0.0.0:0    LISTENING    22100",
                "TCP    0.0.0.0:8080    0.0.0.0:0    TIME_WAIT     0",
                "TCP    127.0.0.1:8080  127.0.0.1:0  ESTABLISHED   0",
            ]
        )

        fake_completed = types.SimpleNamespace(stdout=stdout)

        with patch("doh_http_proxy.subprocess.run", return_value=fake_completed):
            self.assertEqual(
                doh_http_proxy.parse_listening_rows(),
                [("0.0.0.0:8080", 22100)],
            )

    def test_listening_pids_for_target_ignores_zero_pid_rows(self) -> None:
        with patch(
            "doh_http_proxy.parse_listening_rows",
            return_value=[("0.0.0.0:8080", 22100), ("0.0.0.0:8080", 0)],
        ):
            pids, details = doh_http_proxy.listening_pids_for_target("0.0.0.0", 8080)

        self.assertEqual(pids, [22100])
        self.assertEqual(details, ["0.0.0.0:8080 -> PID 22100"])


class StartupConfigTests(unittest.TestCase):
    def test_build_startup_config_uses_persisted_values_and_overrides(self) -> None:
        persisted = doh_http_proxy.StartupConfig(
            listen="127.0.0.1",
            port=9999,
            set_system_proxy=False,
            doh_file="saved-doh.txt",
            use_doh_proxy=False,
            output="saved.txt",
        )
        args = types.SimpleNamespace(use_doh_proxy=True)

        with patch(
            "doh_http_proxy.load_saved_startup_config",
            return_value=persisted,
        ):
            config = doh_http_proxy.build_startup_config_from_namespace(args)

        self.assertEqual(config.listen, "127.0.0.1")
        self.assertEqual(config.port, 9999)
        self.assertFalse(config.set_system_proxy)
        self.assertEqual(config.doh_file, "saved-doh.txt")
        self.assertTrue(config.use_doh_proxy)
        self.assertEqual(config.output, "saved.txt")

    def test_save_persistent_startup_config_round_trips(self) -> None:
        config_path = os.path.join(os.getcwd(), "_startup_config_test.json")
        config = doh_http_proxy.StartupConfig(
            listen="127.0.0.1",
            port=9000,
            use_doh_proxy=False,
            verbose=True,
        )

        try:
            if os.path.exists(config_path):
                os.unlink(config_path)

            with patch(
                "doh_http_proxy.get_startup_config_path",
                return_value=config_path,
            ):
                doh_http_proxy.save_persistent_startup_config(config)
                loaded = doh_http_proxy.load_startup_config(config_path, delete=False)
        finally:
            if os.path.exists(config_path):
                os.unlink(config_path)

        self.assertEqual(loaded, config)

    def test_launch_elevated_frozen_app_command_line(self) -> None:
        shell_execute = types.SimpleNamespace(ShellExecuteW=Mock(return_value=33))
        with patch.object(doh_http_proxy, "os", types.SimpleNamespace(name="nt", path=os.path)), patch.object(
            doh_http_proxy, "ctypes", types.SimpleNamespace(windll=types.SimpleNamespace(shell32=shell_execute))
        ), patch.object(doh_http_proxy, "sys", types.SimpleNamespace(executable="C:\\app\\doh_http_proxy.exe", frozen=True)):
            self.assertTrue(
                doh_http_proxy.launch_elevated(
                    r"C:\Users\TAHA\AppData\Local\Temp\_MEI28402\doh_http_proxy.py",
                    r"C:\Temp\startup-config.json",
                )
            )

        shell_execute.ShellExecuteW.assert_called_once_with(
            None,
            "runas",
            r"C:\app\doh_http_proxy.exe",
            r'--config-file "C:\Temp\startup-config.json"',
            None,
            1,
        )

    def test_interactive_menu_waits_after_proxy_start_error(self) -> None:
        config = doh_http_proxy.StartupConfig(auto_change_hosts=False)

        with patch.object(doh_http_proxy, "render_menu"), patch.object(
            doh_http_proxy, "_read_key", side_effect=[336] * 13 + [13, 27]
        ), patch.object(doh_http_proxy, "save_persistent_startup_config"), patch.object(
            doh_http_proxy, "start_proxy_session", return_value=2
        ), patch.object(doh_http_proxy, "wait_for_menu_key") as wait_for_key:
            result = doh_http_proxy.run_interactive_menu(config)

        self.assertEqual(result, 0)
        wait_for_key.assert_called_once_with()

    def test_elevated_interactive_session_returns_to_menu_after_proxy_stops(self) -> None:
        parser = types.SimpleNamespace(
            parse_args=Mock(return_value=types.SimpleNamespace(config_file="config.json"))
        )
        config = doh_http_proxy.StartupConfig()

        with patch.object(doh_http_proxy, "build_arg_parser", return_value=parser), patch.object(
            doh_http_proxy, "load_namespace_from_config_file", return_value=types.SimpleNamespace(config_file="config.json")
        ), patch.object(
            doh_http_proxy, "build_startup_config_from_namespace", return_value=config
        ), patch.object(doh_http_proxy, "save_persistent_startup_config"), patch.object(
            doh_http_proxy, "should_show_menu", return_value=False
        ), patch.object(doh_http_proxy, "start_proxy_session", return_value=0), patch.object(
            doh_http_proxy, "should_return_to_menu_after_session", return_value=True
        ), patch.object(doh_http_proxy, "run_interactive_menu", return_value=0) as run_menu:
            result = doh_http_proxy.main()

        self.assertEqual(result, 0)
        run_menu.assert_called_once_with(config)


if __name__ == "__main__":
    unittest.main()
