import streamlit as st
import pandas as pd
import ipaddress

# Page layout configuration
st.set_page_config(page_title="Network Config Generator", page_icon="🔌", layout="wide")

st.title("🔌 Network Config & CLI Script Generator")
st.write("Input your project details, parse subnets, and configure interfaces dynamically.")

# Setup columns for the top configuration panel
col1, col2 = st.columns(2)

with col1:
    st.subheader("🏗️ Project & Device Details")
    hostname = st.text_input("Device Hostname", value="Switch-Core-01")
    device_model = st.selectbox("Switch Model", ["Cisco Catalyst 9300", "Cisco Catalyst 2960X"])
    enable_secret = st.text_input("Enable Secret Password", type="password", value="Cisco123!")

with col2:
    st.subheader("🧮 Subnet Parsing & Validation")
    subnet_input = st.text_input("Enter Baseline IPv4 Network (CIDR)", value="192.168.10.0/24")
    
    # Live Subnet Parsing Engine
    try:
        network = ipaddress.ip_network(subnet_input, strict=False)
        st.success(f"✅ Valid Network Found: {network.network_address}")
        
        # Display parsed network parameters
        sub_col1, sub_col2, sub_col3 = st.columns(3)
        sub_col1.metric("Netmask", str(network.netmask))
        sub_col2.metric("First Host", str(network.network_address + 1))
        sub_col3.metric("Total IPs", str(network.num_addresses - 2))
        
        default_ip = str(network.network_address + 1)
        default_mask = str(network.netmask)
    except ValueError:
        st.error("❌ Invalid CIDR format. Please use notation like 10.0.0.0/24")
        default_ip = "192.168.1.1"
        default_mask = "255.255.255.0"

st.divider()

# Interactive Topology Table Section
st.subheader("🗺️ Interactive Interface Topology Table")
st.write("Modify the table below to map out your switchports and IP routes dynamically.")

# Seed data for the interactive spreadsheet UI
initial_topology = pd.DataFrame([
    {"Interface": "GigabitEthernet1/0/1", "Description": "Uplink to Firewall", "Mode": "Trunk", "VLAN": 10, "IP Address": "N/A", "Subnet Mask": "N/A"},
    {"Interface": "GigabitEthernet1/0/2", "Description": "Management SVI", "Mode": "Routed / SVI", "VLAN": 10, "IP Address": default_ip, "Subnet Mask": default_mask},
    {"Interface": "GigabitEthernet1/0/3", "Description": "Engineering Workstations", "Mode": "Access", "VLAN": 20, "IP Address": "N/A", "Subnet Mask": "N/A"},
    {"Interface": "GigabitEthernet1/0/4", "Description": "IP Phones Trunk", "Mode": "Access", "VLAN": 30, "IP Address": "N/A", "Subnet Mask": "N/A"},
])

# Render the interactive spreadsheet UI
edited_df = st.data_editor(
    initial_topology,
    num_rows="dynamic", # Allows network engineers to add/delete interfaces on the fly
    use_container_width=True,
    column_config={
        "Mode": st.column_config.SelectboxColumn("Mode", options=["Access", "Trunk", "Routed / SVI"], required=True),
        "VLAN": st.column_config.NumberColumn("VLAN ID", min_value=1, max_value=4094),
    }
)

st.divider()

# Compile the final script from both configurations dynamically
st.subheader("📋 Generated CLI Configuration Script")

cli_script = f"""! --- Generated Cisco IOS Base Configuration ---
! Device Model: {device_model}
!
hostname {hostname}
!
enable secret {enable_secret}
!
aaa new-model
!
"""

# Iterate through the interactive topology data to construct scripts
for index, row in edited_df.iterrows():
    cli_script += f"interface {row['Interface']}\n"
    if row['Description']:
        cli_script += f" description {row['Description']}\n"
        
    if row['Mode'] == "Access":
        cli_script += f" switchport mode access\n switchport access vlan {row['VLAN']}\n"
    elif row['Mode'] == "Trunk":
        cli_script += f" switchport mode trunk\n"
    elif row['Mode'] == "Routed / SVI":
        if row['IP Address'] != "N/A":
            cli_script += f" no switchport\n ip address {row['IP Address']} {row['Subnet Mask']}\n"
    cli_script += "!\n"

cli_script += "end\nwrite memory"

# Output code window
st.code(cli_script, language="bash")

# Configuration export download anchor
st.download_button(
    label="📥 Download CLI Configuration File (.cfg)",
    data=cli_script,
    file_name=f"{hostname}_config.cfg",
    mime="text/plain"
)
