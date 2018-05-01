""" Base class for butt builders
    implements common functionallity
"""

import glob
import ipaddress
import os
import re
import random
import shutil
import string
import subprocess
import hashlib
from sh import kubectl  # pylint:disable=E0611

import buttlib


class ButtBuilder(object):
    """base class set up parameters needed by all butt builders"""

    def __init__(self, env_info, args):
        self._env_info = env_info
        self._args = args
        self._master_ip_offset = 10
        self._worker_ip_offset = 30
        __ssh_pub_key_helper = buttlib.helpers.SSHKeyHelper()
        __subnet_mask =  24
        __subnet_offset = 0
        __cluster_name = "{}-{}".format(args.cenv, args.cid)
        __buttdir_base = args.buttdir if args.buttdir is not None else os.path.expanduser("~")
        if 'network' in self._env_info:
            if 'subnetMask' in self._env_info['network']:
                __subnet_mask = self._env_info['network']['subnetMask']
            if 'subnetOffset' in self._env_info['network']:
                __subnet_offset = self._env_info['network']['subnetOffset']
        self._butt_ips = buttlib.common.ButtIps(network=self._env_info['externalNet'], subnet_mask=__subnet_mask, subnet_offset=__subnet_offset)
        self._cluster_internal_ips = buttlib.common.ButtIps(network=self._env_info['clusterNet'])
        # huge dict for convience in passing values to user_data
        self._cluster_info = {
            "cenv": args.cenv,
            "cid": args.cid,
            "cloud_provider": "",
            "network_plugin": "cni",
            "cluster_cidr": "172.16.0.0/12",
            "network_config": "",
            "cluster_name": "{}-{}".format(self._args.cenv, self._args.cid),
            "dns_ip": self._cluster_internal_ips.get_ip(5),
            "master_ip": self._butt_ips.get_ip(self._master_ip_offset),
            "kube_master": self._butt_ips.get_ip(self._master_ip_offset),  # wtf?
            "master_port": 443,
            "cluster_ip": self._cluster_internal_ips.get_ip(1),
            "ssh_pub_keys": __ssh_pub_key_helper.get_pub_keys(),
            "optional_hostname_override": "",
            "master_count": env_info['masters']['nodes'],
            "additional_labels": "",
            "nameserver_config": "",
            "hostsfile": "",
            "resolvconf": "",
            "dashboardFQDN": "dashboard-{}.weave.local".format(args.cid),
            "base_image": "coreos_image.img",
            "coreos_image": "coreos_production_qemu_image.img.bz2",
            "ipOffsets": {
                "masters": 10,
                "workers": 30
            },
            "etcd_version": "v3.3.4",
        }
        # these need cluster_name to be set first
        self._cluster_info["etcd_hosts"] = self.get_etcd_hosts()
        self._cluster_info["etcd_initial_cluster"] = self.get_initial_cluster()
        self._cluster_info["kube_masters"] = self.get_kube_masters()
        self._cluster_info["kube_addons"] = self.get_kube_addons()
        self._cluster_info["kube_manifests"] = self.get_kube_manifests()
        self._cluster_info["buttdir"] = "{}/{}".format(__buttdir_base, __cluster_name)
        self._cluster_info["user_data_tmpl"] = {
            "master": self.__read_ud_template("master"),
            "worker": self.__read_ud_template("worker")
        }
        self._cluster_info["etcd_initial_cluster_token"] = hashlib.sha256(self._cluster_info["etcd_initial_cluster"].encode()).hexdigest()
        if 'network' in self._env_info and 'networkName' in self._env_info['network']:
            self._cluster_info['network_name'] = self._env_info['network']['networkName']

        print(self._cluster_info['buttdir'])
        if not os.path.exists(self._cluster_info['buttdir']):
            os.makedirs(self._cluster_info['buttdir'])

    @staticmethod
    def __read_ud_template(ud_type):
        try:
            with open("butt-templates/{}/user_data_tmpl.yaml".format(ud_type), 'r') as file:
                return file.read()
        except IOError as exc:
            print(exc)

    def get_kube_masters(self):
        """:returns: list - k8s api endpoints"""
        return ','.join(
            ["https://%s" % (master) for master in self.get_master_hosts()])

    def get_master_hosts(self):
        """:returns: list - master host names"""
        return [
            "kube-master-%s-%02d" % (self._cluster_info['cluster_name'], i + 1)
            for i in range(self._env_info['masters']['nodes'])
        ]

    def get_worker_hosts(self):
        """DEPRICATED - convert to non-deterministic hostnames
        :returns: list of worker hostsnames"""
        return [
            "kube-worker-%s-%02d" % (self._cluster_info['cluster_name'], i + 1)
            for i in range(self._env_info['workers']['nodes'])
        ]

    def get_master_ips(self):
        """:returns: list of master ip addresses"""
        if "ipOffsets" in self._cluster_info:
            offset = self._cluster_info['ipOffsets']['masters']
        else:
            offset = self._master_ip_offset
        return [
            str(
                ipaddress.IPv4Network(self._env_info['externalNet'])[i + offset])
            for i in range(self._env_info['masters']['nodes'])
        ]

    def get_initial_cluster(self):
        """:returns: - string - etcd initial cluster string"""
        masters = self.get_master_hosts()
        return ",".join([
            "%s=http://%s:2380" % (master, master)
            for index, master in enumerate(masters)
        ])

    def get_etcd_hosts(self):
        """:returns: string - comma delimeted string of proto://host:port"""
        return ",".join(
            ["http://%s:2379" % master for master in self.get_master_hosts()])

    def update_kube_config(self):
        """ Add new context into kube config"""
        update = 'n'
        update = input("Auto update kube config? (y|n)")
        if update == 'y':
            if os.path.isfile(
                    "{}/.kube/config".format(os.path.expanduser("~"))):
                shutil.copy(
                    "{}/.kube/config".format(os.path.expanduser("~")),
                    "{}/.kube/config.bak".format(os.path.expanduser("~")))
            kubectl(
                "config", "set-cluster", "{}-{}-cluster".format(
                    self._cluster_info['cenv'],
                    self._cluster_info['cid']),
                "--server=https://{}:{}".format(
                    self._cluster_info["kube_master"],
                    self._cluster_info["master_port"]),
                "--certificate-authority={}/ssl/ca.pem".format(self._cluster_info['buttdir']))
            kubectl(
                "config", "set-credentials", "{}-{}-admin".format(
                    self._cluster_info['cenv'],
                    self._cluster_info['cid']),
                "--certificate-authority={}/ssl/ca.pem".format(self._cluster_info['buttdir']),
                "--client-key={}/ssl/admin-key.pem".format(self._cluster_info['buttdir']),
                "--client-certificate={}/ssl/admin.pem".format(self._cluster_info['buttdir']))
            kubectl("config", "set-context", "{}-{}-system".format(
                self._cluster_info['cenv'],
                self._cluster_info['cid']),
                    "--cluster={}-{}-cluster".format(
                        self._cluster_info['cenv'],
                        self._cluster_info['cid']),
                    "--user={}-{}-admin".format(
                        self._cluster_info['cenv'],
                        self._cluster_info['cid']))
            kubectl("config", "use-context", "{}-{}-system".format(
                self._cluster_info['cenv'],
                self._cluster_info['cid']))

    def fetch_image(self):
        """downloads the CoreOS image"""
        download = 'y'
        print("Fetching CoreOS image")
        cmd = "curl -sSL https://{}.release.core-os.net/amd64-usr/current/{} | bzcat > {}/{}".format(
            self._env_info['coreosChannel'], self._cluster_info['coreos_image'], self._cluster_info['buttdir'],
            self._cluster_info['base_image'])
        if os.path.isfile(self._cluster_info['buttdir'] + "/" + self._cluster_info['base_image']):
            download = input(
                "%s exists, download anyway? (y|n) " % self._cluster_info['base_image'])
        if download == 'y':
            subprocess.run(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                universal_newlines=True)

    def get_worker_ip(self, index):
        """:returns: string - ip in externalNet range"""
        return str(
            ipaddress.IPv4Network(self._env_info['externalNet'])[
                index + self._worker_ip_offset])

    def get_kube_addons(self):
        """:returns: string - everything in butt-templates/addons converted to string"""
        addons = []
        for addon in glob.glob("butt-templates/addons/*.yaml"):
            with open(addon, 'r') as file:
                temp = file.read()
            if re.search("dashboard-ingress", addon):
                temp = temp.format(dashboardFQDN=self._cluster_info['dashboardFQDN'])
            addons.append({
                "path":
                "/etc/kubernetes/addons/%s" % (os.path.basename(addon)),
                "content":
                temp,
                "permissions":
                "0644",
                "owner":
                "root"
            })
        return addons

    @staticmethod
    def get_kube_manifests():
        """:returns: dict of strings - everything in butt-templates/manifets/* converted to string"""
        manifests = {'master': [], 'worker': []}
        for name in ['master', 'worker']:
            for manifest in glob.glob(
                    "butt-templates/manifests/%s/*.yaml" % name):
                with open(manifest, 'r') as file:
                    temp = file.read()
                manifests[name].append({
                    "path":
                    "/etc/kubernetes/manifests/%s" %
                    (os.path.basename(manifest)),
                    "content":
                    temp,
                    "permissions":
                    "0644",
                    "owner":
                    "root"
                })
        return manifests

    @staticmethod
    def random_mac():
        """:returns: string - random mac starting 52:54:00"""
        mac = [
            0x52, 0x54, 0x00, random.randint(0x00, 0x7f), random.randint(
                0x00, 0xff), random.randint(0x00, 0xff)
        ]
        return ':'.join(map(lambda x: "%02x" % x, mac))

    @staticmethod
    def get_hostname_suffix(suffix_length=5):
        """:returns: string - random string of chars"""
        return ''.join(
            random.choice(string.ascii_lowercase + string.digits)
            for _ in range(suffix_length))
