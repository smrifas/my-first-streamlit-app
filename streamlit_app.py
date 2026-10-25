import streamlit as st

# Configure the page layout and title
st.set_page_config(page_title="Network Config Generator", page_icon="🔌", layout="wide")

st.title("🔌 Network Config & CLI Script Generator")
st.write("Input your project details below to instantly generate standardized Cisco IOS switch configurations.")

# Organize inputs into columns for cleaner UI
col1, col2 = st.columns(2)

with col1:
    st.subheader("🏗️ Project & Device Details")
    hostname = st.text_input("Device Hostname", value="Switch-Core-01")
    device_model = st.selectbox("Switch Model", ["Cisco Catalyst 9300", "Cisco Catalyst 2960X", "Generic Layer 2"])
    
    st.subheader("🔐 Security Settings")
    enable_secret = st.text_input("Enable Secret Password", type="password", value="Cisco123!")
    domain_name = st.text_input("Domain Name (for SSH)", value="yourdomain.local")

with col2:
    st.subheader("🌐 VLAN Definitions")
    st.write("Define your baseline structural VLANs:")
    
    vlan_data = [
        {"id": st.number_input("Management VLAN ID", min_value=1, max_value=4094, value=10),
         "name": st.text_input("Management VLAN Name", value="MGMT")},
        {"id": st.number_input("Data VLAN ID", min_value=1, max_value=4094, value=20),
         "name": st.text_input("Data VLAN Name", value="DATA_USERS")},
        {"id": st.number_input("Voice VLAN ID", min_value=1, max_value=4094, value=30),
         "name": st.text_input("Voice VLAN Name", value="VOIP_PHONES")}
    ]

st.divider()

# Logic to compile the CLI Configuration Script dynamically
st.subheader("📋 Generated CLI Configuration Script")

cli_script = f"""! --- Generated Cisco IOS Base Configuration ---
! Device Model: {device_model}
!
hostname {hostname}
!
ip domain-name {domain_name}
!
enable secret {enable_secret}
!
username admin privilege 15 secret AdminSecure123!
!
aaa new-model
aaa authentication login default local
aaa authorization exec default local
!
crypto key generate rsa general-keys modulus 2048
!
line vty 0 4
 transport input ssh
 login authentication default
!
"""

# Dynamically append VLAN script blocks loop
for vlan in vlan_data:
    cli_script += f"vlan {vlan['id']}\n name {vlan['name']}\n!\n"

cli_script += """!
interface GigabitEthernet1/0/1
 description Uplink to Firewall
 switchport mode trunk
!
end
write memory
"""

# Render the script in a neat, code-styled copyable box
st.code(cli_script, language="bash")

# Add a convenient download button for engineers to save the file locally
st.download_button(
    label="📥 Download CLI Configuration File (.cfg)",
    data=cli_script,
    file_name=f"{hostname}_config.cfg",
    mime="text/plain"
)
