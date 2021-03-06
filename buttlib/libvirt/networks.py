r"""
Do things with libvirt virtual networks.

Exports:
  - get(client: libvirt.virConnect, name: str)
  - list(client: libvirt.virConnect)
  - create(client: libvirt.virConnect, network_config: dic)
  - delete(client: libvirt.virConnect, name: str)
"""

import libvirt
from xml.dom import minidom


__UPDATE_FLAGS = libvirt.VIR_NETWORK_UPDATE_AFFECT_LIVE | libvirt.VIR_NETWORK_UPDATE_AFFECT_CONFIG

xmldesc_tmplt = """<network>
  <name>{name}</name>
  <forward mode='nat'/>
  <bridge name='{bridgename}' stp='on' delay='0'/>
  <mac address='{mac}'/>
  <ip address='{ip}' netmask='{netmask}'>
    <dhcp>
      <range start='{ip_range_start}' end='{ip_range_end}'/>
    </dhcp>
  </ip>
</network>"""

dhcp_entry_tmplt = "<host mac='{mac}' name='{hostname}' ip='{ip}'/>"


def get(client: libvirt.virConnect, name: str) -> libvirt.virNetwork:
    """Get virtual network by name

    Args:

        client: (libvirt.virConnect) connection to libvirt

        name (str) name of network

    Returns:

        libvirt.virConnect or None
    """
    network = None
    try:
        network = client.connection.networkLookupByName(name)
    except libvirt.libvirtError as exc:
        print(exc)
    return network


def list(client: libvirt.virConnect) -> list:
    """### Retrieve list of all networks.
    #### Params
        client: libvirt.virConnect
            connection to libvirt
    #### Returns
        list of libvirt.virNetwork object or []
    """
    try:
        networks = client.connection.listAllNetworks()
    except libvirt.libvirtError as exc:
        print(exc)
        networks = []
    return networks


def create(client: libvirt.virConnect, network_config: dict) ->libvirt.virNetwork:
    """Create and set a network to autostart

    Args:

        client: (libvirt.virConnect) connection to libvirt

        network_config (dict) network info - ip, bridge, ...

    Returns:

        libvirt.virConnect or None
    """
    try:
        if 'bridgename' not in network_config:
            # max length of bridge name is 15 characters
            network_config['bridgename'] = network_config['name'].replace("-", "")[:12] + "br0"
        networkXML = xmldesc_tmplt.format(**network_config)
        network = client.connection.networkDefineXML(networkXML)
        network.create()
        if 'autostart' in network_config and network_config['autostart']:
            network.setAutostart(1)
    except libvirt.libvirtError:
        network = None
    return network


def delete(client: libvirt.virConnect, name: str):
    retval = False
    try:
        network = get(client, name)
        if network:
            network.destroy()
            network.undefine()
            retval = True
    except libvirt.libvirtError as exc:
        print(exc)
        retval = False
    return retval


def exists(client, name):
    exists = False
    networks = list(client)
    for network in networks:
        if network.name() == name:
            exists = True
            break
    return exists


# info on network.update arguments
# 1. command - https://libvirt.org/html/libvirt-libvirt-network.html#virNetworkUpdateCommand
# 2. section - https://libvirt.org/html/libvirt-libvirt-network.html#virNetworkUpdateSection
# 3. parentIndex - -1 for don't care
# 4. xml
# 5. flags
def dhcp_add(client: libvirt.virConnect, dhcp_config) -> bool:
    """
    ### Add entry to a network's dhcp config
    #### Params
        client: libvirt.virConnect
            connecttion to libvirt
        dhcp_config: dict
            ip, mac, ...
    #### Returns
        bool
    """
    retval = False
    try:
        network = get(client, dhcp_config['network_name'])
        if network:
            dhcp_xml = dhcp_entry_tmplt.format(**dhcp_config)
            network.update(libvirt.VIR_NETWORK_UPDATE_COMMAND_ADD_LAST, libvirt.VIR_NETWORK_SECTION_IP_DHCP_HOST, -1, dhcp_xml, __UPDATE_FLAGS)
            retval = True
    except libvirt.libvirtError as exc:
        print(exc)
    return retval


def dhcp_delete(client, dhcp_config):
    retval = False
    try:
        network = get(client, dhcp_config['network_name'])
        if network:
            dhcp_xml = dhcp_entry_tmplt.format(**dhcp_config)
            network.update(libvirt.VIR_NETWORK_UPDATE_COMMAND_DELETE, libvirt.VIR_NETWORK_SECTION_IP_DHCP_HOST, -1, dhcp_xml, __UPDATE_FLAGS)
            retval = True
    except libvirt.libvirtError as exc:
        print(exc)
    return retval


def dhcp_delete_by_name(client, dhcp_config):
    retval = False
    try:
        network = get(client, dhcp_config['network_name'])
        if network:
            network_xml = minidom.parseString(network.XMLDesc())
            dhcp_entries = network_xml.getElementsByTagName("host")
            for entry in dhcp_entries:
                print(entry.attributes['name'].value)
                if entry.attributes['name'].value == dhcp_config['hostname']:
                    tmp_dhcp_config = {
                        "hostname": entry.attributes['name'].value,
                        "ip": entry.attributes['ip'].value,
                        "mac": entry.attributes['mac'].value,
                        "network_name": dhcp_config['network_name']
                    }
                    retval = dhcp_delete(client, tmp_dhcp_config)
                    break
    except libvirt.libvirtError as exc:
        print(exc)
    return retval


def dhcp_delete_by_ip(client, dhcp_config):
    retval = False
    try:
        network = get(client, dhcp_config['network_name'])
        if network:
            network_xml = minidom.parseString(network.XMLDesc())
            dhcp_entries = network_xml.getElementsByTagName("host")
            for entry in dhcp_entries:
                if entry.attributes['ip'].value == dhcp_config['ip']:
                    tmp_dhcp_config = {
                        "hostname": entry.attributes['name'].value,
                        "ip": entry.attributes['ip'].value,
                        "mac": entry.attributes['mac'].value,
                        "network_name": dhcp_config['network_name']
                    }
                    retval = dhcp_delete(client, tmp_dhcp_config)
                    break
    except libvirt.libvirtError as exc:
        print(exc)
    return retval
