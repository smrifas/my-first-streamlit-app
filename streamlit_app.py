import streamlit as st
import pandas as pd
import ipaddress
import math
import json
import os
import re
import hmac


REFERENCE_BITRATES = {
    "1080p": {
        "H.264": 4.0,
        "H.265": 2.0,
    },
    "4K": {
        "H.264": 16.0,
        "H.265": 8.0,
    },
}


def calculate_bitrate(resolution, fps, compression):
    """Estimate bitrate for one camera from a 30 FPS reference bitrate."""
    reference = REFERENCE_BITRATES[resolution][compression]
    return reference * (fps / 30)


def calculate_storage_tb(bandwidth_mbps, retention_days):
    """Calculate storage requirements in decimal terabytes."""
    return bandwidth_mbps / 8 / 1000 * 86400 * retention_days / 1000


def calculate_cctv(camera_quantity, resolution, fps, compression, retention_days):
    """Calculate per-camera bitrate, total bandwidth, and storage."""
    bitrate_per_camera = calculate_bitrate(resolution, fps, compression)
    total_bandwidth = bitrate_per_camera * camera_quantity
    storage_tb = calculate_storage_tb(total_bandwidth, retention_days)
    return bitrate_per_camera, total_bandwidth, storage_tb


def validate_dhcp_scope(scope):
    """Validate and normalize imported or user-entered DHCP scope data."""
    name = scope.get("name", "").strip()
    network = ipaddress.ip_network(scope.get("network", ""), strict=True)
    gateway = ipaddress.ip_address(scope.get("gateway", ""))
    dns = ipaddress.ip_address(scope.get("dns", ""))
    option43 = scope.get("option43", "").strip()
    option60 = scope.get("option60", "").strip()

    if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise ValueError("Pool name may contain only letters, digits, underscores, and hyphens.")
    if network.version != 4 or gateway.version != 4 or dns.version != 4:
        raise ValueError("Use IPv4 CIDR, gateway, and DNS addresses.")
    if gateway not in network or gateway in (
        network.network_address,
        network.broadcast_address,
    ):
        raise ValueError("The gateway must be a usable address in the scope subnet.")
    if dns in (network.network_address, network.broadcast_address):
        raise ValueError("The DNS server cannot be the network or broadcast address.")
    if option43 and not re.fullmatch(r"(?:[0-9A-Fa-f]{2})+", option43):
        raise ValueError("Option 43 must be an even-length hexadecimal string.")
    if option60 and not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", option60):
        raise ValueError("Option 60 must be 1-64 safe ASCII letters, digits, '.', '_', ':', or '-'.")

    return {
        "name": name,
        "network": str(network),
        "gateway": str(gateway),
        "dns": str(dns),
        "option43": option43,
        "option60": option60,
    }


# --- PAGE SETUP ---
st.set_page_config(
    page_title="ELV/IoT Pre-Commissioning Orchestrator",
    page_icon="🔌",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- PROFESSIONAL ENGINEERING THEME ---
st.markdown("""
<style>
    /* 1. Global Background & Font Tuning */
    .stApp {
        background-color: #0b0f19 !important;
        color: #d1d5db !important;
        font-family: 'Courier New', Courier, monospace !important;
    }

    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background-color: #0f1423 !important;
        border-right: 2px solid #1e293b !important;
    }
    section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h3 {
        color: #38bdf8 !important;
        text-transform: uppercase;
        letter-spacing: 1px;
    }

    /* 3. Navigation Tabs Style Override */
    button[data-testid="stMarkdownContainer"] p {
        font-weight: bold !important;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #0f1423;
        padding: 8px;
        border-radius: 8px;
        border: 1px solid #1e293b;
    }
    .stTabs [data-baseweb="tab"] {
        height: 45px;
        white-space: pre-wrap;
        background-color: #1e293b;
        border-radius: 4px;
        color: #9ca3af !important;
        transition: all 0.3s ease;
    }
    .stTabs [aria-selected="true"] {
        background-color: #0284c7 !important;
        color: #ffffff !important;
        border: 1px solid #38bdf8;
        box-shadow: 0 0 10px rgba(56, 189, 248, 0.4);
    }

    /* 4. Sub-Containers & Card Formatting */
    div[data-testid="stForm"], .stDataFrame, .stCodeBlock {
        background-color: #111827 !important;
        border: 1px solid #1e293b !important;
        border-radius: 8px !important;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.5) !important;
    }

    /* Project identity banner */
    .commissioning-header {
        background-color: rgba(56, 189, 248, 0.1);
        border: 2px solid #0284c7;
        padding: 15px;
        border-radius: 6px;
        color: #38bdf8;
        font-weight: bold;
        text-transform: uppercase;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

st.markdown(
    '<div class="commissioning-header">ELV / IoT Pre-Commissioning Orchestrator</div>',
    unsafe_allow_html=True
)

# --- STATE MANAGEMENT ---
if "vlsm_subnets" not in st.session_state:
    st.session_state.vlsm_subnets = []
if "switches" not in st.session_state:
    st.session_state.switches = {
        "SW-01-CORE": {
            "tier": "Core/Distribution", "vlans": "10,20,30,40,50,60",
            "ports": [], "stp_priority": 4096, "poe_budget_watts": 740.0,
        },
        "SW-02-EDGE-CCTV": {
            "tier": "Access Layer", "vlans": "30",
            "ports": [], "stp_priority": 32768, "poe_budget_watts": 370.0,
        },
        "SW-03-EDGE-IOT": {
            "tier": "Access Layer", "vlans": "40,50,60",
            "ports": [], "stp_priority": 32768, "poe_budget_watts": 370.0,
        },
    }
for existing_switch in st.session_state.switches.values():
    existing_switch.setdefault("tier", "Access Layer")
    existing_switch.setdefault(
        "stp_priority",
        4096 if existing_switch["tier"] == "Core/Distribution" else 32768,
    )
    existing_switch.setdefault("poe_budget_watts", 370.0)
if "cctv_config" not in st.session_state:
    st.session_state.cctv_config = {
        "qty": 10, "res": "1080p", "fps": 15, "comp": "H.265", "days": 30
    }

DEVICE_PROFILES = {
    "IP Camera (CCTV)": {
        "bandwidth": 4.0, "vlan": 30, "power": "PoE (802.3af)",
        "watts": 15.4, "traffic": "Multicast / UDP",
    },
    "Smart Access Control Reader": {
        "bandwidth": 0.5, "vlan": 40, "power": "PoE (802.3af)",
        "watts": 6.5, "traffic": "Unicast / TCP-TLS",
    },
    "VoIP Intercom Station": {
        "bandwidth": 2.0, "vlan": 50, "power": "PoE (802.3af)",
        "watts": 12.9, "traffic": "Real-time RTP",
    },
    "BMS Controller Hub": {
        "bandwidth": 1.0, "vlan": 60, "power": "Non-PoE",
        "watts": 0.0, "traffic": "BACnet/IP",
    },
    "Environmental Sensor Cluster": {
        "bandwidth": 0.1, "vlan": 60, "power": "Non-PoE",
        "watts": 0.0, "traffic": "MQTT / Polling",
    },
}
if "dhcp_scopes" not in st.session_state:
    st.session_state.dhcp_scopes = []

app_password = os.environ.get("NETOPS_APP_PASSWORD")
if app_password and not st.session_state.get("authenticated", False):
    st.title("🔐 Secure Infrastructure Authorization")
    with st.form("auth_form"):
        entered_password = st.text_input("Application password", type="password")
        authenticate = st.form_submit_button("Sign in")
        if authenticate:
            if hmac.compare_digest(entered_password, app_password):
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Access refused. Check the application password.")
    st.stop()

# --- SIDEBAR SYSTEM ---
st.sidebar.title("💾 System Workspace")
if "pending_project_name" in st.session_state:
    st.session_state.project_name = st.session_state.pop("pending_project_name")
project_name = st.sidebar.text_input(
    "Active Project Name", value="ELV_METRO_STATION_A", key="project_name"
)
vendor = st.sidebar.radio(
    "Target Switch Vendor", ["Cisco IOS-XE", "Juniper JunOS"]
)
domain = st.sidebar.text_input(
    "Infrastructure Domain", value="elv.internal"
)
hostname = st.sidebar.text_input("Core Switch Hostname", value="HQ-CORE-SW-01")
enable_pwd = st.sidebar.text_input(
    "Optional CLI Enable Secret",
    type="password",
    help="Only inserted into generated CLI when supplied."
)
enforce_ssh = st.sidebar.checkbox("Enforce SSH v2 Only", value=True)
disable_telnet = st.sidebar.checkbox("Restrict VTY to SSH", value=True)
banner_text = st.sidebar.text_area(
    "Login Warning Banner", value="WARNING: Authorized access only."
)

if not app_password:
    st.sidebar.info(
        "Authentication is disabled. Set NETOPS_APP_PASSWORD to enable the login gate."
    )

project_cctv_config = {
    "qty": st.session_state.get("cctv_qty", st.session_state.cctv_config["qty"]),
    "res": st.session_state.get("cctv_resolution", st.session_state.cctv_config["res"]),
    "fps": st.session_state.get("cctv_fps", st.session_state.cctv_config["fps"]),
    "comp": st.session_state.get(
        "cctv_compression", st.session_state.cctv_config["comp"]
    ),
    "days": st.session_state.get("cctv_days", st.session_state.cctv_config["days"]),
}
project_payload = {
    "project_name": project_name,
    "vlsm_subnets": st.session_state.vlsm_subnets,
    "switches": st.session_state.switches,
    "cctv_config": project_cctv_config,
    "dhcp_scopes": st.session_state.dhcp_scopes,
}
st.sidebar.download_button(
    "📥 Save & Export Project Package",
    data=json.dumps(project_payload, indent=2),
    file_name=f"{project_name}_workspace.json",
    mime="application/json",
)
uploaded_workspace = st.sidebar.file_uploader(
    "📤 Restore Workspace Profile", type=["json"]
)
restore_workspace = st.sidebar.button(
    "Restore Uploaded Workspace",
    disabled=uploaded_workspace is None,
)
if uploaded_workspace is not None and restore_workspace:
    try:
        loaded_data = json.load(uploaded_workspace)
        if not isinstance(loaded_data, dict):
            raise ValueError("Workspace must contain a JSON object.")
        loaded_switches = loaded_data.get("switches", {})
        loaded_subnets = loaded_data.get("vlsm_subnets", [])
        loaded_cctv = loaded_data.get("cctv_config", {})
        loaded_dhcp_scopes = loaded_data.get("dhcp_scopes", [])
        if not isinstance(loaded_switches, dict) or any(
            not isinstance(item, dict)
            or not isinstance(item.get("ports", []), list)
            or not isinstance(item.get("vlans", ""), str)
            or not re.fullmatch(r"[A-Za-z0-9_.-]+", switch_name)
            or item.get("tier", "Access Layer") not in ("Access Layer", "Core/Distribution")
            or not (
                isinstance(item.get("stp_priority", 32768), (int, str))
                and str(item.get("stp_priority", 32768)).isdigit()
                and int(item.get("stp_priority", 32768)) in range(0, 61441, 4096)
            )
            or not isinstance(item.get("poe_budget_watts", 370.0), (int, float))
            or item.get("poe_budget_watts", 370.0) < 0
            or not all(
                token.strip().isdigit() and 1 <= int(token.strip()) <= 4094
                for token in item.get("vlans", "").split(",")
            )
            or any(
                not isinstance(port, dict)
                or not isinstance(port.get("port"), str)
                or not re.fullmatch(r"[A-Za-z][A-Za-z0-9/.:_-]*", port.get("port", ""))
                or port.get("device") not in DEVICE_PROFILES
                or not isinstance(port.get("vlan"), int)
                or not 1 <= port.get("vlan", 0) <= 4094
                or not isinstance(port.get("power"), str)
                or (
                    "watts" in port
                    and (
                        not isinstance(port.get("watts"), (int, float))
                        or port.get("watts") < 0
                    )
                )
                or (
                    "bandwidth" in port
                    and not (
                        isinstance(port.get("bandwidth"), (int, float))
                        or port.get("bandwidth") == "Dynamic"
                    )
                )
                for port in item.get("ports", [])
            )
            for switch_name, item in loaded_switches.items()
        ):
            raise ValueError("Switch configuration has an invalid structure.")
        if (
            not isinstance(loaded_subnets, list)
            or not isinstance(loaded_cctv, dict)
            or not isinstance(loaded_dhcp_scopes, list)
        ):
            raise ValueError("Workspace subnet or CCTV data has an invalid structure.")
        for subnet in loaded_subnets:
            if not isinstance(subnet, dict) or not isinstance(subnet.get("name"), str) or not isinstance(subnet.get("hosts"), int):
                raise ValueError("Subnet entries must include a name and integer host count.")
        cctv_options = {
            "res": ("1080p", "4K"),
            "fps": (15, 30),
            "comp": ("H.264", "H.265"),
        }
        for key, allowed_values in cctv_options.items():
            if loaded_cctv.get(key, st.session_state.cctv_config[key]) not in allowed_values:
                raise ValueError(f"CCTV setting '{key}' has an unsupported value.")
        for key in ("qty", "days"):
            value = loaded_cctv.get(key, st.session_state.cctv_config[key])
            if not isinstance(value, int) or value < 1:
                raise ValueError(f"CCTV setting '{key}' must be a positive integer.")
        if any(not isinstance(scope, dict) for scope in loaded_dhcp_scopes):
            raise ValueError("DHCP scope entries have an invalid structure.")
        loaded_dhcp_scopes = [
            validate_dhcp_scope(scope) for scope in loaded_dhcp_scopes
        ]
        loaded_networks = [
            ipaddress.ip_network(scope["network"])
            for scope in loaded_dhcp_scopes
        ]
        if any(
            first.overlaps(second)
            for index, first in enumerate(loaded_networks)
            for second in loaded_networks[index + 1:]
        ):
            raise ValueError("DHCP scope subnets must not overlap.")
        for scope in loaded_dhcp_scopes:
            if any(not isinstance(scope[field], str) for field in (
                "name", "network", "gateway", "dns", "option43", "option60"
            )):
                raise ValueError("DHCP scope entries have an invalid structure.")
        st.session_state.vlsm_subnets = loaded_subnets
        for switch_data in loaded_switches.values():
            switch_data.setdefault("tier", "Access Layer")
            switch_data["stp_priority"] = int(switch_data.get(
                "stp_priority",
                4096 if switch_data["tier"] == "Core/Distribution" else 32768,
            ))
            switch_data.setdefault("poe_budget_watts", 370.0)
            for port in switch_data["ports"]:
                port.setdefault(
                    "bandwidth",
                    DEVICE_PROFILES[port["device"]]["bandwidth"],
                )
                port.setdefault("watts", DEVICE_PROFILES[port["device"]]["watts"])
                port.setdefault("traffic", DEVICE_PROFILES[port["device"]]["traffic"])
        st.session_state.switches = loaded_switches
        st.session_state.cctv_config = {
            **st.session_state.cctv_config,
            **loaded_cctv,
        }
        st.session_state.dhcp_scopes = loaded_dhcp_scopes
        for widget_key in (
            "cctv_qty", "cctv_resolution", "cctv_fps",
            "cctv_compression", "cctv_days",
        ):
            st.session_state.pop(widget_key, None)
        imported_project_name = loaded_data.get("project_name")
        if isinstance(imported_project_name, str) and imported_project_name.strip():
            st.session_state.pending_project_name = imported_project_name.strip()
        st.sidebar.success("Workspace restored.")
        st.rerun()
    except (json.JSONDecodeError, ValueError) as error:
        st.sidebar.error(f"Unable to restore workspace: {error}")

st.sidebar.subheader("🛠️ Hardware Sourcing Profile")
st.markdown(
    f"**Project:** {project_name} &nbsp; | &nbsp; **Vendor:** {vendor} "
    f"&nbsp; | &nbsp; **Domain:** {domain}"
)

# --- NAVIGATION TABS ---
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "🧮 Subnet Partitioning",
    "🎛️ Multi-Switch & VLAN Manager",
    "🛡️ VLAN Isolation & DHCP",
    "🗺️ Interface Topology Editor",
    "📋 Legacy CLI Generator",
    "📹 CCTV Storage Matrix",
    "📋 Commissioning Report",
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
        if root_net.version != 4:
            raise ValueError("Only IPv4 CIDR blocks are supported for this design.")
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
    allocation_table = []
    if st.session_state.vlsm_subnets and root_net:

        # Sort by largest host requirements first
        sorted_demands = sorted(
            st.session_state.vlsm_subnets,
            key=lambda x: x['hosts'],
            reverse=True
        )

        current_pointer = root_net.network_address
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
                    "Wildcard Mask": str(temp_net.hostmask),
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
# TAB 2: MULTI-SWITCH & VLAN MANAGER
# ==========================================
with tab2:
    st.header("🎛️ Multi-Switch & VLAN Manager")
    st.write(
        "Model switch nodes, allowed VLANs, and endpoint-to-port assignments. "
        "Generated output is a reviewable configuration template; it is not pushed to devices."
    )

    with st.expander("➕ Provision a Switch", expanded=False):
        with st.form("new_switch_form", clear_on_submit=True):
            new_switch_name = st.text_input(
                "Switch Hostname", placeholder="e.g. SW-04-EDGE-BUILDING"
            )
            new_switch_tier = st.selectbox(
                "Deployment Tier", ["Access Layer", "Core/Distribution"]
            )
            new_switch_vlans = st.text_input(
                "Allowed VLAN IDs (comma-separated)", value="10,20,30"
            )
            new_switch_priority = st.selectbox(
                "Rapid-PVST+ Bridge Priority",
                options=list(range(0, 61441, 4096)),
                index=1 if new_switch_tier == "Core/Distribution" else 8,
            )
            new_switch_poe_budget = st.number_input(
                "PoE Budget (Watts)", min_value=0.0, value=370.0, step=10.0
            )
            create_switch = st.form_submit_button("Add Switch")
            if create_switch:
                switch_name_clean = new_switch_name.strip()
                vlan_tokens = [token.strip() for token in new_switch_vlans.split(",")]
                if not re.fullmatch(r"[A-Za-z0-9_.-]+", switch_name_clean):
                    st.error("Use only letters, digits, periods, underscores, and hyphens in the switch hostname.")
                elif switch_name_clean in st.session_state.switches:
                    st.error("A switch with that hostname already exists.")
                elif not all(token.isdigit() and 1 <= int(token) <= 4094 for token in vlan_tokens):
                    st.error("VLAN IDs must be integers from 1 through 4094.")
                elif len(set(vlan_tokens)) != len(vlan_tokens):
                    st.error("Remove duplicate VLAN IDs.")
                else:
                    st.session_state.switches[switch_name_clean] = {
                        "tier": new_switch_tier,
                        "vlans": ",".join(vlan_tokens),
                        "ports": [],
                        "stp_priority": new_switch_priority,
                        "poe_budget_watts": new_switch_poe_budget,
                    }
                    st.rerun()

    if not st.session_state.switches:
        st.info("No switch nodes are configured.")

    for switch_name, switch_data in list(st.session_state.switches.items()):
        with st.container(border=True):
            switch_col, port_col, action_col = st.columns([2, 4, 1])
            with switch_col:
                st.markdown(f"### 🖥️ {switch_name}")
                switch_data["tier"] = st.selectbox(
                    "Deployment tier",
                    ["Access Layer", "Core/Distribution"],
                    index=["Access Layer", "Core/Distribution"].index(
                        switch_data.get("tier", "Access Layer")
                    ),
                    key=f"tier_{switch_name}",
                )
                st.write(f"Allowed VLANs: {switch_data['vlans']}")
                st.caption(f"STP root preference: {switch_data['stp_priority']} (lower is preferred)")
                priority_options = list(range(0, 61441, 4096))
                switch_data["stp_priority"] = st.selectbox(
                    "Rapid-PVST+ priority",
                    priority_options,
                    index=priority_options.index(
                        switch_data.get(
                            "stp_priority",
                            4096 if switch_data["tier"] == "Core/Distribution" else 32768,
                        )
                    ),
                    key=f"stp_priority_{switch_name}",
                    help="Lower bridge priority wins root election; valid values use 4096 increments.",
                )
                switch_data["poe_budget_watts"] = st.number_input(
                    "PoE power budget (W)",
                    min_value=0.0,
                    value=float(switch_data.get("poe_budget_watts", 370.0)),
                    step=10.0,
                    key=f"poe_budget_{switch_name}",
                )
            with port_col:
                device_type = st.selectbox(
                    "Endpoint profile",
                    options=list(DEVICE_PROFILES),
                    key=f"device_profile_{switch_name}",
                )
                port_id = st.text_input(
                    "Physical interface",
                    value="GigabitEthernet0/1",
                    key=f"physical_port_{switch_name}",
                )
                if st.button("Bind Endpoint", key=f"bind_endpoint_{switch_name}"):
                    profile = DEVICE_PROFILES[device_type]
                    port = port_id.strip()
                    allowed_vlan_ids = {
                        token.strip()
                        for token in switch_data["vlans"].split(",")
                    }
                    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9/.:_-]*", port):
                        st.error("Enter a valid single-line interface identifier.")
                    elif str(profile["vlan"]) not in allowed_vlan_ids:
                        st.error(
                            f"Add VLAN {profile['vlan']} to this switch's allowed VLAN list first."
                        )
                    elif any(existing["port"] == port for existing in switch_data["ports"]):
                        st.error("That interface already has an endpoint binding.")
                    else:
                        switch_data["ports"].append({
                            "port": port,
                            "device": device_type,
                            "vlan": profile["vlan"],
                            "power": profile["power"],
                            "bandwidth": profile["bandwidth"],
                            "watts": profile["watts"],
                            "traffic": profile["traffic"],
                        })
                        st.rerun()
            with action_col:
                if st.button("Remove", key=f"remove_switch_{switch_name}"):
                    del st.session_state.switches[switch_name]
                    st.rerun()
            if switch_data["ports"]:
                st.dataframe(
                    pd.DataFrame(switch_data["ports"]),
                    use_container_width=True,
                    hide_index=True,
                )
            allocated_poe = sum(
                port.get("watts", DEVICE_PROFILES[port["device"]]["watts"])
                for port in switch_data["ports"]
            )
            st.metric(
                "PoE Power Budget",
                f"{allocated_poe:.1f} / {switch_data['poe_budget_watts']:.1f} W",
                delta=f"{switch_data['poe_budget_watts'] - allocated_poe:.1f} W remaining",
                delta_color="normal" if allocated_poe <= switch_data["poe_budget_watts"] else "inverse",
            )
            if allocated_poe > switch_data["poe_budget_watts"]:
                st.error(f"PoE budget exceeded by {allocated_poe - switch_data['poe_budget_watts']:.1f} W.")

    st.subheader(f"Generated {vendor} Configuration Preview")
    switch_config_lines = []
    for switch_name, switch_data in st.session_state.switches.items():
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", switch_name):
            st.error(f"Switch hostname '{switch_name}' contains unsupported characters.")
            continue
        allowed_vlans = [token.strip() for token in switch_data["vlans"].split(",")]
        if not all(token.isdigit() and 1 <= int(token) <= 4094 for token in allowed_vlans):
            st.error(f"Switch {switch_name} has invalid allowed VLAN IDs.")
            continue
        if vendor == "Cisco IOS-XE":
            switch_config_lines.extend([
                f"! Switch: {switch_name}",
                f"hostname {switch_name}",
                f"ip domain-name {domain}",
                "spanning-tree mode rapid-pvst",
                f"spanning-tree vlan {','.join(allowed_vlans)} priority {switch_data['stp_priority']}",
            ])
            for vlan_id in allowed_vlans:
                switch_config_lines.extend([f"vlan {vlan_id}", f" name VLAN_{vlan_id}"])
            for port in switch_data["ports"]:
                if str(port["vlan"]) not in allowed_vlans:
                    st.error(
                        f"Endpoint VLAN {port['vlan']} is not allowed on switch {switch_name}."
                    )
                    continue
                switch_config_lines.extend([
                    f"interface {port['port']}",
                    f" description Connected_to_{port['device'].replace(' ', '_')}",
                    " switchport mode access",
                    f" switchport access vlan {port['vlan']}",
                    " spanning-tree portfast",
                    " no shutdown",
                ])
                if port.get("watts", 0) > 0:
                    switch_config_lines.append(" power inline auto")
            switch_config_lines.append("!")
        else:
            switch_config_lines.append(f"## Switch: {switch_name}")
            switch_config_lines.append(f"set system host-name {switch_name}")
            switch_config_lines.append(f"set system domain-name {domain}")
            for vlan_id in allowed_vlans:
                switch_config_lines.append(
                    f"set vlans VLAN_{vlan_id} vlan-id {vlan_id}"
                )
                switch_config_lines.append(
                    f"set protocols vstp vlan VLAN_{vlan_id} bridge-priority "
                    f"{switch_data['stp_priority']}"
                )
            for port in switch_data["ports"]:
                if str(port["vlan"]) not in allowed_vlans:
                    st.error(
                        f"Endpoint VLAN {port['vlan']} is not allowed on switch {switch_name}."
                    )
                    continue
                juniper_port = port["port"].replace("GigabitEthernet", "ge-")
                switch_config_lines.append(
                    f"set interfaces {juniper_port} unit 0 family ethernet-switching "
                    f"interface-mode access vlan members VLAN_{port['vlan']}"
                )
    switch_config = "\n".join(switch_config_lines)
    st.code(switch_config or "No valid switch configuration to display.", language="text")
    st.download_button(
        "📥 Download Switch Configuration Preview",
        data=switch_config,
        file_name=f"{project_name}_switch_config.txt",
        mime="text/plain",
        disabled=not switch_config,
    )

# ==========================================
# TAB 3: VLAN ISOLATION ACL & DHCP
# ==========================================
with tab3:
    st.header("🛡️ VLAN Isolation & DHCP Scope Builder")
    st.write(
        "Generate reviewable Cisco IOS policy and DHCP templates from VLSM allocations. "
        "Templates are not applied to devices automatically."
    )
    st.subheader("Inter-VLAN Isolation ACL")
    if not allocation_table or root_net is None:
        st.info("Allocate IPv4 subnet segments in the VLSM tab to build ACLs.")
        acl_config = ""
    else:
        subnet_labels = [
            f"{entry['Segment Name']} ({entry['Allocated Range']})"
            for entry in allocation_table
        ]
        selected_subnet_label = st.selectbox(
            "Source VLAN/subnet to isolate",
            subnet_labels,
            key="acl_source_subnet",
        )
        selected_subnet = allocation_table[subnet_labels.index(selected_subnet_label)]
        source_network = ipaddress.ip_network(selected_subnet["Allocated Range"])
        routed_interface = st.text_input(
            "Routed VLAN interface for ACL attachment",
            value="Vlan30",
            key="acl_routed_interface",
        ).strip()
        acl_name = re.sub(
            r"[^A-Za-z0-9_]",
            "_",
            selected_subnet["Segment Name"].upper(),
        ).strip("_")[:32] or "SEGMENT"
        nvr_address = st.text_input(
            "Optional permitted NVR / management host IPv4 address",
            key="acl_permitted_host",
            help="When set, traffic to this host is permitted before blocking routes within the allocated root supernet.",
        ).strip()
        acl_lines = [
            f"ip access-list extended ACL_{acl_name}_ISOLATION",
            f" remark Isolate configured segment traffic within root network {root_net}",
        ]
        if nvr_address:
            try:
                nvr_ip = ipaddress.ip_address(nvr_address)
                if nvr_ip.version != 4:
                    raise ValueError("Only IPv4 addresses are supported.")
                acl_lines.append(
                    f" permit ip {source_network.network_address} "
                    f"{source_network.hostmask} host {nvr_ip}"
                )
            except ValueError as error:
                st.error(f"Invalid permitted host address: {error}")
                nvr_address = ""
        acl_lines.extend([
            f" deny ip {source_network.network_address} {source_network.hostmask} "
            f"{root_net.network_address} {root_net.hostmask}",
            f" permit ip {source_network.network_address} {source_network.hostmask} any",
        ])
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9/.:_-]*", routed_interface):
            st.error("Enter a valid routed interface name.")
        else:
            acl_lines.extend([
                "!",
                f"interface {routed_interface}",
                f" ip access-group ACL_{acl_name}_ISOLATION in",
            ])
        acl_config = "\n".join(acl_lines)
        st.code(acl_config, language="text")
        st.caption(
            "Review permit order and bind the ACL to the correct routed VLAN interface before deployment."
        )

    st.subheader("DHCP Scopes and IoT Options")
    with st.form("dhcp_scope_form", clear_on_submit=True):
        dhcp_col1, dhcp_col2 = st.columns(2)
        with dhcp_col1:
            scope_name = st.text_input("Pool name", placeholder="CCTV_VLAN30")
            scope_cidr = st.text_input("Network CIDR", placeholder="10.100.30.0/24")
            scope_gateway = st.text_input("Default gateway IPv4", placeholder="10.100.30.1")
            scope_dns = st.text_input("DNS server IPv4", placeholder="10.100.10.10")
        with dhcp_col2:
            scope_option43 = st.text_input(
                "Option 43 payload (hex, without 0x)",
                help="Optional hexadecimal vendor-specific DHCP payload.",
            )
            scope_option60 = st.text_input(
                "Option 60 vendor class (ASCII)",
                help="Optional client vendor-class identifier; validate option handling for your DHCP server.",
            )
        add_scope = st.form_submit_button("Add DHCP Scope")
        if add_scope:
            try:
                validated_scope = validate_dhcp_scope({
                    "name": scope_name,
                    "network": scope_cidr,
                    "gateway": scope_gateway,
                    "dns": scope_dns,
                    "option43": scope_option43,
                    "option60": scope_option60,
                })
                if any(scope["name"] == validated_scope["name"] for scope in st.session_state.dhcp_scopes):
                    raise ValueError("A DHCP pool with that name already exists.")
                new_network = ipaddress.ip_network(validated_scope["network"])
                if any(
                    new_network.overlaps(ipaddress.ip_network(scope["network"]))
                    for scope in st.session_state.dhcp_scopes
                ):
                    raise ValueError("DHCP scope subnets must not overlap an existing pool.")
                st.session_state.dhcp_scopes.append(validated_scope)
                st.rerun()
            except ValueError as error:
                st.error(f"Unable to add DHCP scope: {error}")

    dhcp_lines = []
    if st.session_state.dhcp_scopes:
        st.dataframe(pd.DataFrame(st.session_state.dhcp_scopes), hide_index=True)
        for scope in list(st.session_state.dhcp_scopes):
            if st.button(
                f"Remove DHCP pool {scope['name']}",
                key=f"remove_dhcp_{scope['name']}",
            ):
                st.session_state.dhcp_scopes.remove(scope)
                st.rerun()
        for scope in st.session_state.dhcp_scopes:
            dhcp_network = ipaddress.ip_network(scope["network"])
            dhcp_lines.extend([
                f"ip dhcp excluded-address {scope['gateway']}",
                f"ip dhcp pool {scope['name']}",
                f" network {dhcp_network.network_address} {dhcp_network.netmask}",
                f" default-router {scope['gateway']}",
                f" dns-server {scope['dns']}",
            ])
            if scope["option43"]:
                dhcp_lines.append(f" option 43 hex {scope['option43']}")
            if scope["option60"]:
                dhcp_lines.append(f" option 60 ascii {scope['option60']}")
            dhcp_lines.append("!")
    else:
        st.info("No DHCP pools configured. Add a pool above to generate its template.")

    if dhcp_lines:
        st.code("\n".join(dhcp_lines), language="text")
        st.caption(
            "Cisco IOS-style DHCP template. Confirm DHCP option syntax and vendor-specific Option 43/60 requirements on your target platform."
        )

    with st.expander("Configured template bundle"):
        st.code("\n".join(part for part in (acl_config, "\n".join(dhcp_lines)) if part))

# ==========================================
# TAB 4: INTERACTIVE TOPOLOGY MATRIX
# ==========================================
with tab4:
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
# TAB 5: MULTI-VENDOR CLI ENGINE & COMPLIANCE
# ==========================================
with tab5:
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
!
"""

        if enable_pwd:
            script += f"enable secret {enable_pwd}\n"

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
#  Generated via ELV/IoT Pre-Commissioning Orchestrator
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

# ==========================================
# TAB 6: CCTV BANDWIDTH & STORAGE CALCULATOR
# ==========================================
with tab6:
    st.header("📹 CCTV Network Bandwidth & Storage Calculator")
    st.write(
        "Estimate camera bandwidth and recording storage using planning bitrates. "
        "Use manufacturer- or VMS-specific bitrates when available."
    )

    input_col1, input_col2, input_col3 = st.columns(3)
    with input_col1:
        camera_quantity = st.number_input(
            "Number of Cameras",
            min_value=1,
            value=st.session_state.cctv_config["qty"],
            step=1,
            key="cctv_qty"
        )
        resolution = st.selectbox(
            "Resolution",
            options=["1080p", "4K"],
            index=["1080p", "4K"].index(st.session_state.cctv_config["res"]),
            key="cctv_resolution"
        )
    with input_col2:
        fps = st.selectbox(
            "Frame Rate",
            options=[15, 30],
            format_func=lambda value: f"{value} FPS",
            index=[15, 30].index(st.session_state.cctv_config["fps"]),
            key="cctv_fps"
        )
        compression = st.selectbox(
            "Video Compression",
            options=["H.264", "H.265"],
            index=["H.264", "H.265"].index(st.session_state.cctv_config["comp"]),
            key="cctv_compression"
        )
    with input_col3:
        retention_days = st.number_input(
            "Retention Period (Days)",
            min_value=1,
            value=st.session_state.cctv_config["days"],
            step=1,
            key="cctv_days"
        )

    st.session_state.cctv_config = {
        "qty": camera_quantity,
        "res": resolution,
        "fps": fps,
        "comp": compression,
        "days": retention_days,
    }

    bitrate_per_camera, total_bandwidth, storage_tb = calculate_cctv(
        camera_quantity,
        resolution,
        fps,
        compression,
        retention_days
    )

    st.subheader("Estimated Requirements")
    write_iops = math.ceil(
        total_bandwidth * 1_000_000 / (64 * 1024 * 8)
    )
    result_col1, result_col2, result_col3 = st.columns(3)
    result_col1.metric("Bitrate per Camera", f"{bitrate_per_camera:.2f} Mbps")
    result_col2.metric("Total Network Bandwidth", f"{total_bandwidth:.2f} Mbps")
    result_col3.metric("Required Storage", f"{storage_tb:.2f} TB")
    st.metric(
        "Estimated Continuous Write IOPS",
        f"{write_iops:,}",
        help="Estimate uses 64 KiB writes and the aggregate video bitrate; actual storage IOPS depends on filesystem, RAID, and workload behavior.",
    )

    h264_bandwidth = calculate_bitrate(resolution, fps, "H.264") * camera_quantity
    h265_bandwidth = calculate_bitrate(resolution, fps, "H.265") * camera_quantity
    h264_storage = calculate_storage_tb(h264_bandwidth, retention_days)
    h265_storage = calculate_storage_tb(h265_bandwidth, retention_days)
    storage_saving = (h264_storage - h265_storage) / h264_storage * 100

    st.subheader("Compression Comparison")
    comparison_col1, comparison_col2, comparison_col3 = st.columns(3)
    comparison_col1.metric("H.264 Storage", f"{h264_storage:.2f} TB")
    comparison_col2.metric("H.265 Storage", f"{h265_storage:.2f} TB")
    comparison_col3.metric("H.265 Storage Saving", f"{storage_saving:.1f}%")

    days = list(range(1, retention_days + 1))
    storage_curve = pd.DataFrame(
        {
            "H.264": [
                calculate_storage_tb(h264_bandwidth, day)
                for day in days
            ],
            "H.265": [
                calculate_storage_tb(h265_bandwidth, day)
                for day in days
            ],
        },
        index=days
    )
    storage_curve.index.name = "Retention Period (Days)"

    st.subheader(
        f"CCTV Storage Requirement - "
        f"{camera_quantity} Cameras, {resolution}, {fps} FPS"
    )
    st.line_chart(storage_curve, y_label="Storage Requirement (TB)")

# ==========================================
# TAB 7: FIELD COMMISSIONING REPORT
# ==========================================
with tab7:
    st.header("📋 Field Commissioning Blueprint Report")
    st.write(
        "Review and download a project handover summary for field commissioning."
    )

    report_lines = [
        "=" * 78,
        "ELV / IoT NETWORK INFRASTRUCTURE BRIEF",
        "FIELD COMMISSIONING ENGINEER EXECUTION REPORT",
        "=" * 78,
        f"Project: {project_name}",
        f"Target vendor: {vendor}",
        f"Infrastructure domain: {domain}",
        "",
        "1. IP ADDRESSING & VLSM ALLOCATIONS",
    ]
    if allocation_table:
        for allocation in allocation_table:
            report_lines.extend([
                f"- Segment: {allocation['Segment Name']}",
                f"  Network: {allocation['Allocated Range']}",
                f"  Mask: {allocation['Subnet Mask']}",
                f"  Wildcard mask: {allocation['Wildcard Mask']}",
                f"  Gateway: {allocation['Gateway/First Host']}",
            ])
    else:
        report_lines.append("No VLSM segments have been allocated.")

    report_lines.extend(["", "2. SWITCHES, VLANs & CONNECTED ENDPOINTS"])
    for switch_name, switch_data in st.session_state.switches.items():
        report_lines.extend([
            f"[Switch: {switch_name}]",
            f"Tier: {switch_data.get('tier', 'Access Layer')}",
            f"Allowed VLANs: {switch_data['vlans']}",
            f"Rapid-PVST+ bridge priority: {switch_data.get('stp_priority', 32768)}",
            (
                f"PoE budget: {sum(port.get('watts', DEVICE_PROFILES[port['device']]['watts']) for port in switch_data['ports']):.1f} / "
                f"{switch_data.get('poe_budget_watts', 370.0):.1f} W"
            ),
        ])
        if switch_data["ports"]:
            for port in switch_data["ports"]:
                report_lines.append(
                    f"- {port['port']}: {port['device']} | VLAN {port['vlan']} "
                    f"| {port['power']} | {port.get('bandwidth', 'Unknown')} Mbps "
                    f"| {port.get('watts', DEVICE_PROFILES[port['device']]['watts']):.1f} W"
                )
        else:
            report_lines.append("No endpoint ports assigned.")

    report_lines.extend([
        "",
        "3. CCTV STORAGE & BANDWIDTH ESTIMATE",
        f"Cameras: {camera_quantity}",
        f"Resolution: {resolution}",
        f"Frame rate: {fps} FPS",
        f"Compression: {compression}",
        f"Retention: {retention_days} days",
        f"Bitrate per camera: {bitrate_per_camera:.2f} Mbps",
        f"Aggregate bandwidth: {total_bandwidth:.2f} Mbps",
        f"Estimated storage: {storage_tb:.2f} TB",
        f"Estimated 64 KiB write IOPS: {write_iops:,}",
        "",
        "4. DHCP SCOPES",
    ])
    if st.session_state.dhcp_scopes:
        for scope in st.session_state.dhcp_scopes:
            report_lines.append(
                f"- {scope['name']}: {scope['network']} | gateway {scope['gateway']} "
                f"| DNS {scope['dns']} | Option 43 {'configured' if scope['option43'] else 'not configured'} "
                f"| Option 60 {scope['option60'] or 'not configured'}"
            )
    else:
        report_lines.append("No DHCP scopes configured.")
    report_lines.extend([
        "",
        "5. Generated VLAN isolation ACL template",
        acl_config or "No ACL generated: allocate a VLSM subnet first.",
        "",
        "Planning estimates only; validate against vendor/VMS specifications.",
        "=" * 78,
    ])
    commissioning_report = "\n".join(report_lines)
    st.text_area(
        "Handover Report Preview",
        value=commissioning_report,
        height=420,
    )
    st.download_button(
        "📥 Download Commissioning Report",
        data=commissioning_report,
        file_name=f"COMMISSIONING_REPORT_{project_name}.txt",
        mime="text/plain",
    )
