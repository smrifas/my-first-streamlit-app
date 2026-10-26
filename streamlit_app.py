import streamlit as st
import pandas as pd
import ipaddress
import math
import time
import os


# ============================================================
# NETOPS ENTERPRISE ARCHITECT
# MOI-SSD CCTV NETWORK CONFIGURATION ENGINE
# ============================================================

st.set_page_config(
    page_title="NetOps Enterprise Architect - MOI SSD",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# SESSION STATE
# ============================================================

if "vlsm_subnets" not in st.session_state:
    st.session_state.vlsm_subnets = []


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title("🛠️ Global Parameters")

vendor = st.sidebar.radio(
    "Target NOS Vendor Architecture",
    [
        "Cisco IOS-XE",
        "Juniper JunOS",
        "Arista EOS",
    ],
)

hostname = st.sidebar.text_input(
    "Core Hostname",
    value="QA-SSD-CCTV-SW-01",
)

domain = st.sidebar.text_input(
    "DNS Domain",
    value="moi-compliance.qa",
)

enable_pwd = st.sidebar.text_input(
    "Privileged Secret Password",
    type="password",
    value="MoiSecure2026!",
)


# ============================================================
# COMPLIANCE SETTINGS
# ============================================================

st.sidebar.subheader("🛡️ MOI-SSD & Hardening Rules")

enforce_ssh = st.sidebar.checkbox(
    "Enforce SSH v2 Only",
    value=True,
)

disable_telnet = st.sidebar.checkbox(
    "Explicitly Block Unencrypted VTY",
    value=True,
)

banner_text = st.sidebar.text_area(
    "Login Warning Banner",
    value=(
        "RESTRICTED ACCESS: MOI-SSD Surveillance Network. "
        "Unauthorized access strictly prohibited."
    ),
)


# ============================================================
# MOI SSD CCTV VLAN DATABASE
# ============================================================

SSD_VLANS = {
    50: "MOI_SSD_CCTV_CAMERAS",
    60: "MOI_SSD_CCTV_STORAGE_NVR",
    70: "MOI_SSD_CCTV_VMS_VIEWING",
}


# ============================================================
# NAVIGATION
# ============================================================

tab1, tab2, tab3 = st.tabs(
    [
        "🧮 Subnet Parsing & VLSM Engine",
        "🗺️ Dynamic Topology Editor",
        "📋 Compiled CLI Generation Engine",
    ]
)


# ============================================================
# TAB 1
# VLSM / IPAM ENGINE
# ============================================================

with tab1:

    st.header("🧮 VLSM Network Partitioning & IPAM Tracker")

    st.write(
        "Input your primary supernet allocation and register "
        "required endpoint capacities."
    )

    supernet_input = st.text_input(
        "Root Supernet Allocation (CIDR Block)",
        value="10.200.0.0/16",
    )

    try:
        root_net = ipaddress.ip_network(
            supernet_input,
            strict=False,
        )

        st.success(
            f"🚀 Root Block Validated: {root_net} "
            f"({root_net.num_addresses:,} Total Addresses)"
        )

    except ValueError:

        st.error(
            "❌ Invalid Root Subnet Structure. "
            "Use valid CIDR formatting."
        )

        root_net = None


    st.subheader("📋 Register Local Segment Engineering Demands")

    with st.form(
        "subnet_form",
        clear_on_submit=True,
    ):

        col1, col2 = st.columns(2)

        with col1:

            seg_name = st.text_input(
                "Segment Label / Department Name",
                placeholder="e.g. CCTV-IP-Cameras",
            )

        with col2:

            hosts_needed = st.number_input(
                "Required Host Capacities",
                min_value=2,
                max_value=8192,
                value=120,
                step=1,
            )

        submit_subnet = st.form_submit_button(
            "➕ Append Subnet Tier Allocation"
        )

        if submit_subnet and seg_name and root_net:

            st.session_state.vlsm_subnets.append(
                {
                    "name": seg_name,
                    "hosts": hosts_needed,
                }
            )

            st.success(
                f"Added subnet requirement: {seg_name}"
            )


    if st.button("🗑️ Reset Subnet Matrices"):

        st.session_state.vlsm_subnets = []

        st.rerun()


    # --------------------------------------------------------
    # VLSM CALCULATION
    # --------------------------------------------------------

    if st.session_state.vlsm_subnets and root_net:

        sorted_demands = sorted(
            st.session_state.vlsm_subnets,
            key=lambda x: x["hosts"],
            reverse=True,
        )

        current_pointer = int(root_net.network_address)

        allocation_table = []

        is_exhausted = False


        for sub in sorted_demands:

            needed_ips = sub["hosts"] + 2

            prefix_len = 32 - math.ceil(
                math.log2(needed_ips)
            )

            try:

                temp_net = ipaddress.ip_network(
                    f"{ipaddress.ip_address(current_pointer)}/{prefix_len}",
                    strict=False,
                )

                if not temp_net.subnet_of(root_net):

                    is_exhausted = True
                    break


                allocation_table.append(
                    {
                        "Segment Name": sub["name"],
                        "Requested Hosts": sub["hosts"],
                        "Allocated Range": str(temp_net),
                        "Subnet Mask": str(temp_net.netmask),
                        "Gateway / First Host": str(
                            temp_net.network_address + 1
                        ),
                        "Broadcast Address": str(
                            temp_net.broadcast_address
                        ),
                    }
                )


                current_pointer = (
                    int(temp_net.broadcast_address) + 1
                )


            except ValueError:

                is_exhausted = True
                break


        if is_exhausted:

            st.error(
                "🚨 Address space exhausted. "
                "The requested subnet capacity exceeds "
                "the available supernet."
            )


        allocated_df = pd.DataFrame(
            allocation_table
        )

        if not allocated_df.empty:

            st.dataframe(
                allocated_df,
                use_container_width=True,
                hide_index=True,
            )

    else:

        st.info(
            "💡 Add department requirements above "
            "to run custom VLSM calculations."
        )


# ============================================================
# TAB 2
# TOPOLOGY EDITOR
# ============================================================

with tab2:

    st.header("🗺️ Enterprise Topology Table Mapper")

    st.write(
        "Define switch interfaces, access VLANs, trunks, "
        "and routed/SVI endpoints."
    )


    default_interfaces = pd.DataFrame(
        [
            {
                "Port": "GigabitEthernet1/0/1",
                "Description": "Uplink-to-SSD-Agg-Switch",
                "Profile": "Trunk",
                "VLAN": 1,
                "Static IP": "N/A",
                "Subnet Mask": "N/A",
            },
            {
                "Port": "GigabitEthernet1/0/2",
                "Description": "MOI-SSD-IP-Camera-PTZ-01",
                "Profile": "Access",
                "VLAN": 50,
                "Static IP": "N/A",
                "Subnet Mask": "N/A",
            },
            {
                "Port": "GigabitEthernet1/0/3",
                "Description": "MOI-SSD-NVR-Storage-01",
                "Profile": "Access",
                "VLAN": 60,
                "Static IP": "N/A",
                "Subnet Mask": "N/A",
            },
            {
                "Port": "GigabitEthernet1/0/4",
                "Description": "MOI-Client-VMS-Viewing-Station",
                "Profile": "Access",
                "VLAN": 70,
                "Static IP": "N/A",
                "Subnet Mask": "N/A",
            },
            {
                "Port": "Vlan50",
                "Description": "SVI-CCTV-Camera-Gateway",
                "Profile": "Routed / SVI",
                "VLAN": 50,
                "Static IP": "10.200.50.1",
                "Subnet Mask": "255.255.255.0",
            },
        ]
    )


    edited_topology_df = st.data_editor(
        default_interfaces,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Profile": st.column_config.SelectboxColumn(
                "Port Profile Type",
                options=[
                    "Access",
                    "Trunk",
                    "Routed / SVI",
                ],
                required=True,
            ),
            "VLAN": st.column_config.NumberColumn(
                "VLAN Tag Mapping",
                min_value=1,
                max_value=4094,
                step=1,
            ),
        },
    )


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def safe_vlan(value):
    try:
        return int(value)
    except Exception:
        return 1


def safe_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def mask_to_prefix(mask):

    try:
        return ipaddress.IPv4Network(
            f"0.0.0.0/{mask}"
        ).prefixlen

    except Exception:

        return 24


# ============================================================
# CISCO IOS-XE GENERATOR
# ============================================================

def generate_cisco():

    script = f"""!
! ==========================================================
! NETOPS ENTERPRISE ARCHITECT
! BRAND: Cisco IOS-XE
! COMPLIANCE TARGET: Qatar MOI SSD CCTV
! ==========================================================
!
hostname {hostname}
ip domain-name {domain}
enable secret {enable_pwd}
!
"""


    script += (
        "! ----------------------------------------------------------\n"
        "! MOI-SSD CCTV VLAN SEGREGATION\n"
        "! ----------------------------------------------------------\n"
    )


    for vlan_id, vlan_name in SSD_VLANS.items():

        script += (
            f"vlan {vlan_id}\n"
            f" name {vlan_name}\n"
            "!\n"
        )


    if banner_text:

        script += (
            "banner motd ^C\n"
            f"{banner_text}\n"
            "^C\n"
            "!\n"
        )


    if enforce_ssh:

        script += (
            "ip ssh version 2\n"
            "crypto key generate rsa general-keys modulus 2048\n"
            "!\n"
        )


    for _, row in edited_topology_df.iterrows():

        port = safe_text(row["Port"])
        description = safe_text(row["Description"])
        profile = safe_text(row["Profile"])
        vlan = safe_vlan(row["VLAN"])

        static_ip = safe_text(row["Static IP"])
        subnet_mask = safe_text(row["Subnet Mask"])


        script += f"interface {port}\n"


        if description:

            script += (
                f" description {description}\n"
            )


        if profile == "Access":

            script += (
                " switchport mode access\n"
                f" switchport access vlan {vlan}\n"
                " spanning-tree portfast\n"
            )


        elif profile == "Trunk":

            script += (
                " switchport trunk encapsulation dot1q\n"
                " switchport mode trunk\n"
            )


        elif profile == "Routed / SVI":

            if "Vlan" not in port:

                script += " no switchport\n"


            if static_ip != "N/A" and subnet_mask != "N/A":

                script += (
                    f" ip address {static_ip} "
                    f"{subnet_mask}\n"
                )


        script += (
            " no shutdown\n"
            "!\n"
        )


    if disable_telnet:

        script += (
            "line vty 0 15\n"
            " transport input ssh\n"
            " login local\n"
            "!\n"
        )


    script += (
        "end\n"
        "write memory\n"
    )


    return script


# ============================================================
# JUNIPER JUNOS GENERATOR
# ============================================================

def generate_juniper():

    script = (
        "# ==========================================================\n"
        "# NETOPS ENTERPRISE ARCHITECT\n"
        "# BRAND: Juniper JunOS\n"
        "# COMPLIANCE TARGET: Qatar MOI SSD CCTV\n"
        "# ==========================================================\n\n"
    )


    script += (
        f"set system host-name {hostname}\n"
        f"set system domain-name {domain}\n"
    )


    script += (
        "\n"
        "# ----------------------------------------------------------\n"
        "# MOI-SSD CCTV VLAN SEGREGATION\n"
        "# ----------------------------------------------------------\n"
    )


    for vlan_id, vlan_name in SSD_VLANS.items():

        script += (
            f"set vlans {vlan_name} vlan-id {vlan_id}\n"
        )


    if enforce_ssh:

        script += (
            "set system services ssh protocol-version v2\n"
        )


    for _, row in edited_topology_df.iterrows():

        port = safe_text(row["Port"])
        profile = safe_text(row["Profile"])
        vlan = safe_vlan(row["VLAN"])

        static_ip = safe_text(row["Static IP"])
        subnet_mask = safe_text(row["Subnet Mask"])


        # Cisco-style interface name conversion
        if "GigabitEthernet" in port:

            port = port.replace(
                "GigabitEthernet",
                "ge-",
            )


        if profile == "Access":

            vlan_name = SSD_VLANS.get(
                vlan,
                f"VLAN_{vlan}",
            )

            script += (
                f"set interfaces {port} unit 0 "
                "family ethernet-switching "
                f"interface-mode access "
                f"vlan members {vlan_name}\n"
            )


        elif profile == "Trunk":

            script += (
                f"set interfaces {port} unit 0 "
                "family ethernet-switching "
                "interface-mode trunk "
                "vlan members all\n"
            )


        elif profile == "Routed / SVI":

            if (
                static_ip != "N/A"
                and subnet_mask != "N/A"
            ):

                prefix = mask_to_prefix(
                    subnet_mask
                )

                script += (
                    f"set interfaces {port} unit 0 "
                    f"family inet address "
                    f"{static_ip}/{prefix}\n"
                )


    script += (
        "\n"
        "# Validate before deployment\n"
        "commit check\n"
        "# commit\n"
    )


    return script


# ============================================================
# ARISTA EOS GENERATOR
# ============================================================

def generate_arista():

    script = f"""!
! ==========================================================
! NETOPS ENTERPRISE ARCHITECT
! BRAND: Arista EOS
! COMPLIANCE TARGET: Qatar MOI SSD CCTV
! ==========================================================
!
hostname {hostname}
ip domain-name {domain}
!
"""


    script += (
        "! ----------------------------------------------------------\n"
        "! MOI-SSD CCTV VLAN SEGREGATION\n"
        "! ----------------------------------------------------------\n"
    )


    for vlan_id, vlan_name in SSD_VLANS.items():

        script += (
            f"vlan {vlan_id}\n"
            f" name {vlan_name}\n"
            "!\n"
        )


    for _, row in edited_topology_df.iterrows():

        port = safe_text(row["Port"])
        profile = safe_text(row["Profile"])
        vlan = safe_vlan(row["VLAN"])

        static_ip = safe_text(row["Static IP"])
        subnet_mask = safe_text(row["Subnet Mask"])


        script += (
            f"interface {port}\n"
        )


        if profile == "Access":

            script += (
                " switchport mode access\n"
                f" switchport access vlan {vlan}\n"
            )


        elif profile == "Trunk":

            script += (
                " switchport mode trunk\n"
            )


        elif profile == "Routed / SVI":

            if "Vlan" not in port:

                script += (
                    " no switchport\n"
                )


            if (
                static_ip != "N/A"
                and subnet_mask != "N/A"
            ):

                prefix = mask_to_prefix(
                    subnet_mask
                )

                script += (
                    f" ip address "
                    f"{static_ip}/{prefix}\n"
                )


        script += "!\n"


    script += (
        "end\n"
        "copy running-config startup-config\n"
    )


    return script


# ============================================================
# PACKET TRACER CLIPBOARD BRIDGE
# ============================================================

def generate_packet_tracer_bridge(config):

    escaped_config = config.replace(
        '"""',
        '\\"\\"\\"',
    )


    bridge = f'''# ==========================================================
# PACKET TRACER CLIPBOARD CONFIGURATION BRIDGE
# ==========================================================

import pyperclip
import time
import os


CONFIG_PAYLOAD = """enable
configure terminal
{escaped_config}
"""


def push_config_via_clipboard():

    print(
        "[*] Copying configuration to system clipboard..."
    )

    pyperclip.copy(CONFIG_PAYLOAD)

    print()
    print("[ACTION REQUIRED]")
    print(
        "1. Bring Cisco Packet Tracer to the front."
    )
    print(
        "2. Open the target switch/router CLI."
    )
    print(
        "3. Click inside the black CLI terminal."
    )

    for i in range(5, 0, -1):

        print(
            f"Injecting payload in {{i}} seconds...",
            end="\\\\r",
        )

        time.sleep(1)


    print()
    print(
        "[*] Injecting configuration..."
    )


    if os.name == "nt":

        import ctypes

        VK_SHIFT = 0x10
        VK_INSERT = 0x2D

        ctypes.windll.user32.keybd_event(
            VK_SHIFT,
            0,
            0,
            0,
        )

        ctypes.windll.user32.keybd_event(
            VK_INSERT,
            0,
            0,
            0,
        )

        ctypes.windll.user32.keybd_event(
            VK_INSERT,
            0,
            2,
            0,
        )

        ctypes.windll.user32.keybd_event(
            VK_SHIFT,
            0,
            2,
            0,
        )

        print(
            "[OK] Configuration injected."
        )

    else:

        print(
            "[ERROR] Automatic keyboard injection "
            "is currently optimized for Windows."
        )


if __name__ == "__main__":

    push_config_via_clipboard()
'''


    return bridge


# ============================================================
# TAB 3
# CONFIGURATION ENGINE
# ============================================================

with tab3:

    st.header(
        "📋 Production Compiled Deployment Script"
    )

    st.write(
        "Generate vendor-specific network configuration "
        "from the topology matrix."
    )


    # --------------------------------------------------------
    # GENERATE CONFIGURATION
    # --------------------------------------------------------

    if vendor == "Cisco IOS-XE":

        script = generate_cisco()

        syntax_language = "cisco"


    elif vendor == "Juniper JunOS":

        script = generate_juniper()

        syntax_language = "text"


    else:

        script = generate_arista()

        syntax_language = "bash"


    # --------------------------------------------------------
    # DISPLAY CONFIG
    # --------------------------------------------------------

    st.subheader(
        f"⚙️ Generated {vendor} Configuration"
    )

    st.code(
        script,
        language=syntax_language,
    )


    # --------------------------------------------------------
    # DOWNLOAD CONFIG
    # --------------------------------------------------------

    st.download_button(
        label=(
            f"📥 Download Configuration "
            f"({vendor})"
        ),
        data=script,
        file_name=(
            f"{hostname}_final_delivery.txt"
        ),
        mime="text/plain",
    )


    st.divider()


    # ========================================================
    # PACKET TRACER MODULE
    # ========================================================

    st.subheader(
        "🤖 Packet Tracer Clipboard Automation Module"
    )

    st.write(
        """
        Generates a standalone Python utility that
        copies the compiled configuration to the
        Windows clipboard and injects it into the
        Packet Tracer CLI.
        """
    )


    automation_script = (
        generate_packet_tracer_bridge(script)
    )


    col1, col2 = st.columns(2)


    with col1:

        st.download_button(
            label=(
                f"📥 Download Static CLI Template "
                f"({vendor})"
            ),
            data=script,
            file_name=(
                f"{hostname}_config.txt"
            ),
            mime="text/plain",
        )


    with col2:

        st.download_button(
            label=(
                "⚡ Download Packet Tracer "
                "Clipboard Bridge (.py)"
            ),
            data=automation_script,
            file_name="deploy_to_pt.py",
            mime="text/x-python",
        )


    st.divider()


    # ========================================================
    # COMPLIANCE SUMMARY
    # ========================================================

    st.subheader(
        "🛡️ Generated Compliance Profile"
    )


    compliance_data = pd.DataFrame(
        [
            {
                "Control": "CCTV Camera Network",
                "VLAN": 50,
                "Profile": SSD_VLANS[50],
            },
            {
                "Control": "NVR / Storage",
                "VLAN": 60,
                "Profile": SSD_VLANS[60],
            },
            {
                "Control": "VMS / Viewing Stations",
                "VLAN": 70,
                "Profile": SSD_VLANS[70],
            },
            {
                "Control": "SSH",
                "VLAN": "-",
                "Profile": (
                    "SSH v2 enforced"
                    if enforce_ssh
                    else "Disabled by user"
                ),
            },
            {
                "Control": "Telnet",
                "VLAN": "-",
                "Profile": (
                    "Blocked"
                    if disable_telnet
                    else "Not explicitly blocked"
                ),
            },
        ]
    )


    st.dataframe(
        compliance_data,
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "NetOps Enterprise Architect | "
    "CCTV Network Engineering & Configuration Prototype"
)
