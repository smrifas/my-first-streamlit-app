import streamlit as st
import pandas as pd
import ipaddress
import math

# --- PAGE SETUP ---
st.set_page_config(
    page_title="NetOps Enterprise Architect",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- STATE MANAGEMENT ---
# Initialize custom configuration profile persistent store across edits
if "vlsm_subnets" not in st.session_state:
    st.session_state.vlsm_subnets = []

# --- SIDEBAR SYSTEM ---
st.sidebar.title("🛠️ Global Parameters")
vendor = st.sidebar.radio(
    "Target NOS Vendor Architecture",
    ["Cisco IOS-XE", "Juniper JunOS", "Arista EOS"]
)
hostname = st.sidebar.text_input("Core Hostname", value="HQ-CORE-SW-01")
domain = st.sidebar.text_input("DNS Domain Domain", value="enterprise.net")
enable_pwd = st.sidebar.text_input(
    "Privileged Secret Password",
    type="password",
    value="CiscoSecure2026!"
)

# Compliance rule toggles
st.sidebar.subheader("🛡️ Compliance & Hardening")
enforce_ssh = st.sidebar.checkbox("Enforce SSH v2 Only", value=True)
disable_telnet = st.sidebar.checkbox(
    "Explicitly Block Unencrypted VTY",
    value=True
)
banner_text = st.sidebar.text_area(
    "Login Warning Banner",
    value="WARNING: Authorized Access Only! Activity logged."
)

# --- NAVIGATION TABS ---
tab1, tab2, tab3 = st.tabs([
    "🧮 Subnet Parsing & VLSM Engine",
    "🗺️ Dynamic Topology Editor",
    "📋 Compiled CLI Generation Engine"
])

# ==========================================
# TAB 1: ADVANCED VLSM / IPAM SUB-ENGINE
# ==========================================
with tab1:
    st.header("🧮 VLSM Network Partitioning & IPAM Tracker")
    st.write(
        "Input your primary supernet allocation chunk, then register required department endpoints."
    )

    supernet_input = st.text_input(
        "Root Supernet Allocation (CIDR Block)",
        value="10.100.0.0/16"
    )

    try:
        root_net = ipaddress.ip_network(supernet_input, strict=False)
        st.success(
            f"🚀 Root Block Validated: {root_net} ({root_net.num_addresses:,} Total Addresses)"
        )
    except ValueError:
        st.error(
            "❌ Invalid Root Subnet Structure. Use valid CIDR formatting (e.g. 172.16.0.0/12)"
        )
        root_net = None

    st.subheader("📋 Register Local Segment Engineering Demands")

    # Input panel for dynamic subnet additions
    with st.form("subnet_form", clear_on_submit=True):
        col_s1, col_s2 = st.columns(2)

        with col_s1:
            seg_name = st.text_input(
                "Segment Label / Department Name",
                placeholder="e.g., Engineering-Core"
            )

        with col_s2:
            hosts_needed = st.number_input(
                "Required Host Capacities (Excluding Net/Broadcast)",
                min_value=2,
                max_value=8192,
                value=50
            )

        submit_subnet = st.form_submit_button(
            "➕ Append Subnet Tier Allocation"
        )

        if submit_subnet and seg_name and root_net:
            st.session_state.vlsm_subnets.append({
                "name": seg_name,
                "hosts": hosts_needed
            })

    # Clear state mechanism
    if st.button("🗑️ Reset Subnet Matrices"):
        st.session_state.vlsm_subnets = []
        st.rerun()

    # Calculate allocations using VLSM criteria
    if st.session_state.vlsm_subnets and root_net:

        # Sort by largest host requirements first
        sorted_demands = sorted(
            st.session_state.vlsm_subnets,
            key=lambda x: x['hosts'],
            reverse=True
        )

        current_pointer = root_net.network_address
        allocation_table = []
        is_exhausted = False

        for sub in sorted_demands:
            needed_ips = sub['hosts'] + 2
            prefix_len = 32 - math.ceil(math.log2(needed_ips))

            try:
                temp_net = ipaddress.ip_network(
                    f"{current_pointer}/{prefix_len}",
                    strict=False
                )

                if not temp_net.subnet_of(root_net):
                    is_exhausted = True
                    break

                allocation_table.append({
                    "Segment Name": sub['name'],
                    "Requested Hosts": sub['hosts'],
                    "Allocated Range": str(temp_net),
                    "Subnet Mask": str(temp_net.netmask),
                    "Gateway/First Host": str(temp_net.network_address + 1),
                    "Broadcast Address": str(temp_net.broadcast_address)
                })

                current_pointer = temp_net.broadcast_address + 1

            except ValueError:
                is_exhausted = True

        if is_exhausted:
            st.error(
                "🚨 Out of Address Spaces! Allocated requirements exceed structural supernet block volume bounds."
            )

        allocated_df = pd.DataFrame(allocation_table)
        st.dataframe(
            allocated_df,
            use_container_width=True
        )

    else:
        st.info(
            "💡 Pro-Tip: Add department requirements above to run custom Variable Length Subnet Mask calculations."
        )

# ==========================================
# TAB 2: INTERACTIVE TOPOLOGY MATRIX
# ==========================================
with tab2:
    st.header("🗺️ Enterprise Topology Table Mapper")
    st.write(
        "Define layer structures, map access allocations, or declare explicitly managed SVI endpoints below."
    )

    default_interfaces = pd.DataFrame([
        {
            "Port": "GigabitEthernet1/0/1",
            "Description": "ISP-Primary-Uplink",
            "Profile": "Trunk",
            "VLAN": 1,
            "Static IP": "N/A",
            "Subnet Mask": "N/A"
        },
        {
            "Port": "GigabitEthernet1/0/2",
            "Description": "Corporate-Wireless-AP",
            "Profile": "Trunk",
            "VLAN": 10,
            "Static IP": "N/A",
            "Subnet Mask": "N/A"
        },
        {
            "Port": "Vlan10",
            "Description": "SVI-Management-Gateway",
            "Profile": "Routed / SVI",
            "VLAN": 10,
            "Static IP": "10.100.10.1",
            "Subnet Mask": "255.255.255.0"
        },
        {
            "Port": "GigabitEthernet1/0/3",
            "Description": "FinTech-Workstation-01",
            "Profile": "Access",
            "VLAN": 20,
            "Static IP": "N/A",
            "Subnet Mask": "N/A"
        }
    ])

    edited_topology_df = st.data_editor(
        default_interfaces,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Profile": st.column_config.SelectboxColumn(
                "Port Profile Type",
                options=["Access", "Trunk", "Routed / SVI"],
                required=True
            ),
            "VLAN": st.column_config.NumberColumn(
                "VLAN Tag Mapping",
                min_value=1,
                max_value=4094,
                step=1
            ),
        }
    )

# ==========================================
# TAB 3: MULTI-VENDOR CLI ENGINE & COMPLIANCE
# ==========================================
with tab3:
    st.header("📋 Production Compiled Deployment Script")

    # ------------------------------------------
    # ENGINE BLOCK A: CISCO IOS-XE RENDER ROUTINES
    # ------------------------------------------
    if vendor == "Cisco IOS-XE":

        script = f"""! ########################################################
! BRAND ARCHITECTURE PROFILE: {vendor}
! GENERATED VIA ENTERPRISE APPLICATION CONFIG PARSER ENGINE
! ########################################################
hostname {hostname}
ip domain-name {domain}
enable secret {enable_pwd}
!
"""

        if banner_text:
            script += f"banner motd ^C\n{banner_text}\n^C\n!\n"

        if enforce_ssh:
            script += (
                "ip ssh version 2\n"
                "crypto key generate rsa general-keys modulus 2048\n!\n"
            )

        for _, row in edited_topology_df.iterrows():

            script += f"interface {row['Port']}\n"

            if pd.notna(row['Description']) and row['Description'] != "":
                script += f" description {row['Description']}\n"

            if row['Profile'] == "Access":
                script += (
                    f" switchport mode access\n"
                    f" switchport access vlan {int(row['VLAN'])}\n"
                    " spanning-tree portfast\n"
                )

            elif row['Profile'] == "Trunk":
                script += (
                    " switchport trunk encapsulation dot1q\n"
                    " switchport mode trunk\n"
                )

            elif row['Profile'] == "Routed / SVI":

                if "Vlan" not in str(row['Port']):
                    script += " no switchport\n"

                if row['Static IP'] != "N/A":
                    script += (
                        f" ip address {row['Static IP']} "
                        f"{row['Subnet Mask']}\n"
                    )

            script += " no shutdown\n!\n"

        if disable_telnet:
            script += (
                "line vty 0 15\n"
                " transport input ssh\n"
                " login local\n!\n"
            )

        script += "end\nwrite memory"
        st.code(script, language="bash")

    # ------------------------------------------
    # ENGINE BLOCK B: JUNIPER JUNOS RENDER ROUTINES
    # ------------------------------------------
    elif vendor == "Juniper JunOS":

        script = f"""# ########################################################
# BRAND ARCHITECTURE PROFILE: {vendor} (Set Command Format)
# ########################################################
set system hostname {hostname}
set system domain-name {domain}
set system root-authentication plain-text-password-value "{enable_pwd}"
"""

        if enforce_ssh:
            script += "set system services ssh protocol-version v2\n"

        for _, row in edited_topology_df.iterrows():

            p_name = row['Port']

            if "GigabitEthernet" in p_name:
                p_name = p_name.replace(
                    "GigabitEthernet",
                    "ge-"
                )

            if row['Profile'] == "Access":
                script += (
                    f"set interfaces {p_name} unit 0 "
                    f"family ethernet-switching interface-mode access "
                    f"vlan members {int(row['VLAN'])}\n"
                )

            elif row['Profile'] == "Trunk":
                script += (
                    f"set interfaces {p_name} unit 0 "
                    f"family ethernet-switching interface-mode trunk "
                    f"vlan members all\n"
                )

            elif row['Profile'] == "Routed / SVI":

                if row['Static IP'] != "N/A":
                    script += (
                        f"set interfaces {p_name} unit 0 "
                        f"family inet address "
                        f"{row['Static IP']}/{row['Subnet Mask']}\n"
                    )

        script += "commit check\n# commit"
        st.code(script, language="text")

    # ------------------------------------------
    # ENGINE BLOCK C: ARISTA EOS RENDER ROUTINES
    # ------------------------------------------
    elif vendor == "Arista EOS":

        script = f"""! ########################################################
! BRAND ARCHITECTURE PROFILE: {vendor}
! ########################################################
hostname {hostname}
ip domain-name {domain}
!
"""

        for _, row in edited_topology_df.iterrows():

            script += f"interface {row['Port']}\n"

            if row['Profile'] == "Access":
                script += (
                    f" switchport mode access\n"
                    f" switchport access vlan {int(row['VLAN'])}\n"
                )

            elif row['Profile'] == "Trunk":
                script += " switchport mode trunk\n"

            elif row['Profile'] == "Routed / SVI":

                if "Vlan" not in str(row['Port']):
                    script += " no switchport\n"

                if row['Static IP'] != "N/A":
                    script += (
                        f" ip address {row['Static IP']}/"
                        f"{row['Subnet Mask']}\n"
                    )

            script += "!\n"

        script += "end\ncopy running-config startup-config"
        st.code(script, language="bash")

    # Final Export Trigger Download Wrapper Matrix
    st.download_button(
        label=f"📥 Download Normalized Configuration Template ({vendor})",
        data=script,
        file_name=f"{hostname}_final_delivery.txt",
        mime="text/plain"
    )
    # ==========================================================
    # PACKET TRACER AUTOMATION MODULE
    # ==========================================================

    st.subheader("🤖 Packet Tracer Automated Deployment Module")

    st.write("""
    Pro-Project Feature: Instead of manual copy-pasting, download the companion
    automation wrapper below.

    Running this localized Python block will stream the active configuration
    directly into your active Packet Tracer environment via its external CLI
    engine loop.
    """)

    automation_script_template = f"""# ====================================================================
#  AUTOMATED PACKET TRACER BATCH INTERCONNECT BRIDGE
#  Generated via NetOps Enterprise Architect Engine
# ====================================================================

import socket
import time
import sys


def stream_config_to_simulator(host="127.0.0.1", port=59000):

    config_payload = r'''{script}'''

    print(f"[*] Initializing connection pipeline to Packet Tracer Core at {{host}}:{{port}}...")

    s = None

    try:

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((host, port))

        print("[+] Interprocess Pipeline established. Beginning configuration streaming sequence...")
        time.sleep(1)

        lines = config_payload.splitlines()

        for idx, line in enumerate(lines, 1):

            clean_line = line.strip()

            if clean_line.startswith("!") or clean_line.startswith("#"):
                continue

            if clean_line:

                print(f"   [{{idx}}/{{len(lines)}}] Injecting: {{clean_line}}")

                s.sendall(
                    clean_line.encode("ascii", errors="ignore") + b"\\n"
                )

                time.sleep(0.15)

        print("\\n[============== DEPLOYMENT STATUS ==============]")
        print("[✅] All CLI configuration rows streamed successfully!")
        print("[================================================]")

    except socket.timeout:
        print("\\n[❌] Error: Connection timed out.")

    except ConnectionRefusedError:
        print("\\n[❌] Error: Connection refused by target host.")

    except Exception as e:
        print(f"\\n[❌] Critical Runtime Error: {{e}}")

    finally:
        if s:
            s.close()


if __name__ == "__main__":

    print("=================================================================")
    print(" ENTERPRISE NETOPS PACKET TRACER CONTROLLER ENGINE ")
    print("=================================================================")

    target_port = 59000

    if len(sys.argv) > 1:

        try:
            target_port = int(sys.argv[1])

        except ValueError:
            print("[!] Warning: Invalid port arg. Defaulting to 59000.")

    stream_config_to_simulator(port=target_port)
"""

    btn_col1, btn_col2 = st.columns(2)

    with btn_col1:
        st.download_button(
            label=f"📥 Download Static CLI Template ({vendor})",
            data=script,
            file_name=f"{hostname}_config.txt",
            mime="text/plain"
        )

    with btn_col2:
        st.download_button(
            label="⚡ Download Packet Tracer Execution Bridge (.py)",
            data=automation_script_template,
            file_name="deploy_to_pt.py",
            mime="text/x-python"
        )
