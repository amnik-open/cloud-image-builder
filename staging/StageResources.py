import os
import openstack
import configparser


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


class StageResources:
    def __init__(self):
        self.auth_config = {"auth_url": None, "region_name": None, "project_name": None, "username": None,
                            "password": None, "user_domain_name": "Default", "project_domain_name": "Default",
                            "interface": "public", "endpoint_type": "publicURL"}
        self.image_info = dict()
        self.server_info = dict()
        self._set_auth_config()
        self._set_image_info()
        self._set_server_info()
        self.conn = _create_openstack_connection(**self.auth_config)
        self.keyPair = None
        self.image = None
        self.server = None
        self.network = None
        self.subnet = None
        self.extra_volume = None

    def _set_auth_config(self):
        for k in self.auth_config.keys():
            if os.getenv(k) is not None:
                self.auth_config[k] = os.getenv(k)

    def _set_image_info(self):
        self.image_info["image_path"] = os.getenv("image_path")
        self.image_info["image_name"] = os.getenv("image_name")

    def _set_server_info(self):
        if os.getenv("flavor_name") is not None:
            self.server_info["flavor_name"] = os.getenv("flavor_name")
        else:
            self.server_info["flavor_name"] = "g2-2-1-0"
        if os.getenv("public_network_name") is not None:
            self.server_info["public_network_name"] = os.getenv("public_network_name")
        else:
            self.server_info["public_network_name"] = "public210"
        if os.getenv("server_root_size") is not None:
            self.server_info["server_root_size"] = os.getenv("server_root_size")
        else:
            self.server_info["server_root_size"] = "25"

    def _create_image(self):
        print(f'Create image {self.image_info["image_name"]}')
        properties = configparser.ConfigParser()
        properties.read('staging/properties.ini')
        self.image = self.conn.create_image(name=self.image_info["image_name"], filename=self.image_info["image_path"],
                                            allow_duplicates=True, disk_format='raw', visibility='private',
                                            tags=['personal'], meta=properties[self.image_info["image_name"]])
        self.image_info["image_username"] = properties[self.image_info["image_name"]]["username"]

    def _create_keypair(self):
        print(f"Create keypair gitlab-runner-ssh-key")
        public_key_path = os.getenv("SSH_PUBLIC_KEY_PATH")
        with open(public_key_path, 'r') as public_file:
            public_key = public_file.readline().strip()
        self.keyPair = self.conn.compute.create_keypair(name="gitlab-runner-ssh-key", public_key=public_key)

    def _create_server(self):
        print(f"Create server {self.image_info['image_name']}")
        flavor = self.conn.compute.find_flavor(self.server_info["flavor_name"])
        network = self.conn.network.find_network(self.server_info["public_network_name"])
        block_device_mapping_v2 = [{"boot_index": "0", "uuid": self.image.id,
                                    "source_type": "image", "volume_size": self.server_info["server_root_size"],
                                    "destination_type": "volume", "delete_on_termination": True, "disk_bus": "virtio"}]
        server = self.conn.compute.create_server(name=self.image_info["image_name"],
                                                 block_device_mapping=block_device_mapping_v2,
                                                 flavor_id=flavor.id, networks=[{"uuid": network.id}],
                                                 key_name=self.keyPair.name)
        self.server = self.conn.compute.wait_for_server(server)

    def _create_private_network(self):
        print(f"Create network {self.image_info['image_name']}_network")
        self.network = self.conn.network.create_network(name=f"{self.image_info['image_name']}_network")

    def _create_subnet_network(self):
        print(f"Create subnet {self.image_info['image_name']}_network_subnet")
        self.subnet = self.conn.network.create_subnet(name=f"{self.image_info['image_name']}_network_subnet",
                                                      network_id=self.network.id, cidr='192.168.1.0/24', ip_version='4')

    def _create_extra_volume(self):
        print(f"Create extra volume {self.image_info['image_name']}_extra_volume")
        self.extra_volume = self.conn.block_storage.create_volume(name=f"{self.image_info['image_name']}_extra_volume",
                                                                  size=5)

    def _save_resource_info(self):
        stg_env = ["IMAGE_ID=" + self.image.id + "\n", "SERVER_ID=" + self.server.id + "\n",
                   "SERVER_USERNAME=" + self.image_info["image_username"] + "\n", "SERVER_IP=" +
                   self.server.addresses[self.server_info["public_network_name"]][0]['addr'] + "\n",
                   "KEYPAIR_ID=" + self.keyPair.id + "\n", "SERVER_NAME=" + self.image_info["image_name"] + "\n",
                       "NETWORK_ID=" + self.network.id + "\n", "SUBNET_ID=" + self.subnet.id + "\n", "EXTRA_VOLUME_ID=" +
                   self.extra_volume.id + "\n"]
        with open("stage.env", 'w') as stage:
            stage.writelines(stg_env)

    def stage_resources(self):
        print("Stage resources:")
        self._create_image()
        self._create_keypair()
        self._create_server()
        self._create_private_network()
        self._create_subnet_network()
        self._create_extra_volume()
        self._save_resource_info()
