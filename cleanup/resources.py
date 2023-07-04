import os
import openstack


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


class Resources:
    def __init__(self):
        self.auth_config = {"auth_url": None, "region_name": None, "project_name": None, "username": None,
                            "password": None, "user_domain_name": "Default", "project_domain_name": "Default",
                            "interface": "public", "endpoint_type": "publicURL"}
        self.image_id = os.getenv("IMAGE_ID")
        self.server_id = os.getenv("SERVER_ID")
        self.keypair_id = os.getenv("KEYPAIR_ID")
        self.network_id = os.getenv("NETWORK_ID")
        self.subnet_id = os.getenv("SUBNET_ID")
        self.extra_volume_id = os.getenv("EXTRA_VOLUME_ID")
        self._set_auth_config()
        self.conn = _create_openstack_connection(**self.auth_config)

    def _set_auth_config(self):
        for k in self.auth_config.keys():
            if os.getenv(k) is not None:
                self.auth_config[k] = os.getenv(k)

    def delete_resources(self):
        print("Delete resources:")
        self.conn.image.delete_image(self.image_id)
        print(f"Image {self.image_id} is deleted")
        server = self.conn.compute.find_server(self.server_id)
        self.conn.compute.delete_server(self.server_id, force=True)
        self.conn.compute.wait_for_delete(server)
        print(f"Server {self.server_id} is deleted")
        self.conn.compute.delete_keypair(self.keypair_id)
        print(f"Keypair {self.keypair_id} is deleted")
        self.conn.network.delete_subnet(self.subnet_id)
        print(f"Subnet {self.subnet_id} is deleted")
        self.conn.network.delete_network(self.network_id)
        print(f"Network {self.network_id} is deleted")
        self.conn.block_storage.delete_volume(self.extra_volume_id)
        print(f"Extra volume {self.extra_volume_id} is deleted")
