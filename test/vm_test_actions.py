from fabric import Connection
import time
import openstack
import os
import random
import string


def _create_openstack_connection(auth_url, region_name, project_name, username, password, user_domain_name,
                                 project_domain_name, interface, endpoint_type):
    return openstack.connect(
        auth_url=auth_url,
        project_name=project_name,
        username=username,
        password=password,
        region_name=region_name,
        user_domain_name=user_domain_name,
        project_domain_name=project_domain_name,
        interface=interface,
        endpoint_type=endpoint_type
    )


def _connect_to_gateway(gateway_username, gateway_ip, gateway_port, ssh_key_path):
    gateway = Connection(host=gateway_ip, user=gateway_username,
                         connect_kwargs={"key_filename": ssh_key_path},
                         port=gateway_port, forward_agent=True)
    return gateway


class VmTestActions:
    def __init__(self, gateway_username, gateway_ip, gateway_port, server_username, server_ip, ssh_key_path, server_id,
                 network_id, extra_volume_id):
        self.vmC = None
        self.ssh_parameters = {"gateway_username": gateway_username, "gateway_ip": gateway_ip,
                               "gateway_port": gateway_port, "server_username": server_username, "server_ip": server_ip,
                               "ssh_key_path": ssh_key_path}
        self._prepare_ssh_connection(**self.ssh_parameters)
        self.auth_config = {"auth_url": None, "region_name": None, "project_name": None, "username": None,
                            "password": None, "user_domain_name": "Default", "project_domain_name": "Default",
                            "interface": "public", "endpoint_type": "publicURL"}
        self._set_auth_config()
        self.conn = _create_openstack_connection(**self.auth_config)
        self.stage_info = {"server_id": server_id, "network_id": network_id, "extra_volume_id": extra_volume_id}

    def _set_auth_config(self):
        for k in self.auth_config.keys():
            if os.getenv(k) is not None:
                self.auth_config[k] = os.getenv(k)

    def _prepare_ssh_connection(self, gateway_username, gateway_ip, gateway_port, server_username, server_ip,
                                ssh_key_path):
        gateway = _connect_to_gateway(gateway_username, gateway_ip, gateway_port, ssh_key_path)
        time.sleep(30)
        count = 10
        ssh_service_started = False
        while not ssh_service_started and count > 0:
            try:
                result = gateway.run("nc -zv " + server_ip + " 22")
                ssh_service_started = True
            except:
                time.sleep(6)
                count -= 1
        if not ssh_service_started:
            print("ssh service on abrack is not started")
            exit(1)
        self.vmC = Connection(user=server_username, host=server_ip, gateway=gateway,
                              connect_kwargs={"key_filename": ssh_key_path})

    def get_interfaces_name(self):
        interfaces = self.vmC.run("/usr/sbin/ip -4 -o a | awk '{print $2}'", hide=True)
        return interfaces.stdout.strip()

    def get_hostname(self):
        hostname = self.vmC.run("hostname", hide=True)
        return hostname.stdout.strip()

    def ping_internet(self):
        error = False
        try:
            ping_out = self.vmC.run("ping -c 5 google.com", hide=True)
        except:
            error = True
        if error:
            return "-1"
        else:
            return ping_out.stdout.strip()

    def get_partition_table(self):
        pt = self.vmC.run("/usr/sbin/gdisk -l", hide=True)
        return pt.stdout.strip()

    def get_console_log(self):
        console_log = self.conn.compute.get_server_console_output(self.stage_info['server_id'], length=None)
        return console_log['output']

    def add_server_to_private_network(self):
        self.conn.compute.create_server_interface(self.stage_info["server_id"], net_id=self.stage_info["network_id"])
        time.sleep(20)
        count = 5
        result = None
        while count > 0:
            try:
                eth1_interface = self.vmC.run("/usr/sbin/ip a | grep eth1", hide=True)
                result = eth1_interface.stdout.strip()
                break
            except:
                count -= 1
                time.sleep(10)
        if count == 0:
            result = "-1"
        return result

    def add_extra_volume_to_server(self):
        self.conn.compute.create_volume_attachment(server=self.stage_info["server_id"],
                                                   volume=self.stage_info["extra_volume_id"])
        time.sleep(10)
        disk = self.vmC.run("lsblk | grep vdb", hide=True)
        return disk.stdout.strip()

    def resize_server(self):
        server_id = self.stage_info["server_id"]
        server = self.conn.compute.find_server(server_id)
        self.conn.compute.stop_server(server=server_id)
        self.conn.compute.wait_for_server(server=server, status='SHUTOFF', wait=60)
        volume_attachments = self.conn.compute.volume_attachments(server=server_id)
        root_volume_id = None
        for v in volume_attachments:
            if v.id != self.stage_info["extra_volume_id"]:
                root_volume_id = v.id
                break
        root_volume = self.conn.block_storage.find_volume(root_volume_id)
        new_size = root_volume.size + 7
        self.conn.block_storage.reset_volume_status(volume=root_volume_id, status="available", attach_status="",
                                                    migration_status="")
        self.conn.block_storage.extend_volume(root_volume_id, new_size)
        self.conn.compute.start_server(server=server_id)
        self.conn.compute.wait_for_server(server=server, status='ACTIVE', wait=60)
        self._prepare_ssh_connection(**self.ssh_parameters)
        disk = self.vmC.run("lsblk | grep vda", hide=True)
        return new_size, disk.stdout.strip()

    def change_server_password(self):
        password = ''.join(random.choice(string.ascii_letters) for i in range(8))
        result = None
        try:
            self.conn.compute.change_server_password(server=self.stage_info["server_id"], new_password=password)
            print(f"password {password} is set on server")
            cs_url = self.conn.compute.get_server_console_url(server=self.stage_info["server_id"], console_type='novnc')
            print(f"console url for server id {self.stage_info['server_id']}:")
            print(f"{cs_url['url']}")
            result = password
        except:
            result = "ERROR"
        return result
