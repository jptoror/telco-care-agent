"""Network tools: line status, outages, remote diagnostics and modem reboot."""

from . import data

# Simulated device state changes (a reboot) live for the life of the process.
_overrides: dict[str, dict] = {}


def _device(customer_id: str) -> dict | None:
    d = data.one("devices", customer_id=customer_id)
    return {**d, **_overrides.get(customer_id, {})} if d else None


def _active_outages(zone_id: str) -> list[dict]:
    return [o for o in data.where("outages", zone_id=zone_id) if o["status"] == "ACTIVE"]


def get_line_status(customer_id: str) -> dict:
    """Current status of the customer's home modem (ONLINE, DEGRADED, OFFLINE), signal and last contact."""
    c = data.customer(customer_id)
    d = _device(customer_id)
    if not d:
        return {"customer_id": customer_id, "service": "mobile", "zone_id": c["zone_id"],
                "note": "Mobile-only customer: no home modem."}
    return {"customer_id": customer_id, "service": "home", "zone_id": c["zone_id"], "device_id": d["device_id"],
            "status": d["status"], "signal_dbm": int(d["signal_dbm"]), "last_seen": d["last_seen"]}


def check_zone_outage(customer_id: str) -> dict:
    """Active network outages in the customer's zone, with cause and estimated restoration time."""
    c = data.customer(customer_id)
    outages = _active_outages(c["zone_id"])
    return {"zone_id": c["zone_id"], "active_outage": bool(outages),
            "outages": [{k: o[k] for k in ("outage_id", "cause", "started_at", "eta", "affected")} for o in outages]}


def run_remote_diagnostic(customer_id: str) -> dict:
    """Runs a remote line test and returns a diagnosis code plus the recommended next step."""
    status = get_line_status(customer_id)
    if status["service"] != "home":
        return {"diagnosis": "NOT_APPLICABLE", "next_step": "Mobile line: suggest restarting the phone."}
    outage = check_zone_outage(customer_id)
    if outage["active_outage"]:
        o = outage["outages"][0]
        return {"diagnosis": "ZONE_OUTAGE", "outage_id": o["outage_id"], "eta": o["eta"],
                "next_step": "Inform the outage and ETA. A reboot will not help."}
    if status["status"] == "DEGRADED":
        return {"diagnosis": "MODEM_NEEDS_REBOOT", "signal_dbm": status["signal_dbm"],
                "next_step": "Offer a remote modem reboot (takes ~3 minutes)."}
    if status["status"] == "OFFLINE":
        return {"diagnosis": "NO_SIGNAL_FROM_MODEM",
                "next_step": "Ask to check power and cables; if still offline, hand off for a technician visit."}
    return {"diagnosis": "LINE_OK", "signal_dbm": status["signal_dbm"],
            "next_step": "Line is healthy; check Wi-Fi position, devices connected or run a speed test by cable."}


def reboot_modem(customer_id: str) -> dict:
    """Reboots the customer's modem remotely. Refuses when a zone outage explains the problem."""
    diag = run_remote_diagnostic(customer_id)
    if diag["diagnosis"] == "ZONE_OUTAGE":
        return {"status": "SKIPPED", "reason": "Active zone outage; a reboot would not fix it.",
                "outage_id": diag["outage_id"]}
    if diag["diagnosis"] == "NOT_APPLICABLE":
        return {"status": "SKIPPED", "reason": "Customer has no home modem."}
    if diag["diagnosis"] == "MODEM_NEEDS_REBOOT":
        _overrides[customer_id] = {"status": "ONLINE", "signal_dbm": "-55"}
        return {"status": "DONE", "new_status": "ONLINE", "signal_dbm": -55}
    return {"status": "DONE", "new_status": get_line_status(customer_id)["status"],
            "note": "Reboot completed but the modem state did not change."}


TOOLS = [get_line_status, check_zone_outage, run_remote_diagnostic, reboot_modem]
