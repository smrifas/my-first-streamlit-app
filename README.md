# ELV/IoT Pre-Commissioning Orchestrator

A Streamlit prototype for VLSM/IPAM planning, multi-switch VLAN design,
endpoint assignments, Rapid-PVST+ priorities, PoE budgets, VLAN-isolation ACL
templates, DHCP scopes with optional IoT options, CCTV bandwidth/storage/IOPS,
and site handover reports. Generated network configuration is a reviewable
template, not a live device deployment.
The separate Packet Tracer bridge download is optional and should only be run
against a simulator you control after reviewing its configuration payload.

## Run locally

```powershell
python -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Optional application password

The login gate is disabled unless `NETOPS_APP_PASSWORD` is configured in the
process environment. Set it before launching Streamlit to enable password
authentication; do not store the password in source control.

```powershell
$env:NETOPS_APP_PASSWORD = "replace-with-a-private-password"
streamlit run streamlit_app.py
```

## Project workspace

Use the sidebar controls to save the current project as a JSON workspace or
restore a previously saved JSON workspace. The package contains project
subnets, switch tiers, VLANs, STP priorities, endpoint and PoE mappings, DHCP
scopes, and CCTV parameters.

CCTV bandwidth and storage values are planning estimates based on the
reference bitrates in the app. Replace them with manufacturer- or
VMS-specific values for final sizing. Write IOPS use an illustrative 64 KiB
block assumption. Check ACL placement and DHCP Option 43/60 encoding against
the target vendor documentation before using generated templates.
