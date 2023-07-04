import os
import unittest
from vm_test_actions import VmTestActions


def get_info_connection():
    conn_info = {"gateway_username": os.getenv("GATEWAY_USERNAME"), "gateway_ip": os.getenv("GATEWAY_IP"),
                 "gateway_port": os.getenv("GATEWAY_PORT"), "ssh_key_path": os.getenv("SSH_PRIVATE_KEY_PATH"),
                 "server_username": os.getenv("SERVER_USERNAME"), "server_ip": os.getenv("SERVER_IP"),
                 "server_id": os.getenv("SERVER_ID"), "network_id": os.getenv("NETWORK_ID"), "extra_volume_id":
                 os.getenv("EXTRA_VOLUME_ID")}
    return conn_info


def get_info_resources():
    resource_info = {"server_name": os.getenv("SERVER_NAME")}
    return resource_info


class TestVM(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        conn_info = get_info_connection()
        cls.resource_info = get_info_resources()
        cls.vmAct = VmTestActions(**conn_info)

    def test_interface_name(self):
        interface_names = self.vmAct.get_interfaces_name()
        self.assertIn("eth0", interface_names)

    def test_hostname_change(self):
        hostname = self.vmAct.get_hostname()
        server_name = self.resource_info['server_name']
        server_name = server_name.lower().replace('.', '-')
        server_name_regex = ".*" + server_name + ".*"
        self.assertRegex(hostname, server_name_regex)

    def test_internet_connectivity(self):
        check = self.vmAct.ping_internet()
        self.assertIn("0% packet loss", check, msg="Internet connection has problem")

    def test_partition_table(self):
        pt = self.vmAct.get_partition_table()
        self.assertRegex(pt, "GPT .*", msg="Partition table is not GPT")

    def test_console_log(self):
        cl = self.vmAct.get_console_log()
        self.assertIn("cloud-init", cl, msg="Console log has problem")

    def test_interface_addition(self):
        eth1_interface = self.vmAct.add_server_to_private_network()
        self.assertRegex(eth1_interface, ".*eth1.* UP .*")

    def test_disk_attachment(self):
        vdb_disk = self.vmAct.add_extra_volume_to_server()
        self.assertRegex(vdb_disk, ".*vdb .* 5G .*")

    def test_server_resize(self):
        new_size, vda_disk = self.vmAct.resize_server()
        volume_regex = ".*vda .* " + str(new_size) + "G .*"
        self.assertRegex(vda_disk, volume_regex)

    def test_change_server_password(self):
        password = self.vmAct.change_server_password()
        self.assertNotEqual(password, "ERROR", msg="Change password is not successful")


unittest.main()
