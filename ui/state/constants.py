from __future__ import annotations

import copy

STATUS_OPTIONS = ["Vacant ready", "Vacant not ready", "On notice"]
ASSIGNEE_OPTIONS = ["", "Michael", "Brad", "Miguel A", "Roadrunner", "Make Ready Co"]
BLOCK_OPTIONS = ["Not Blocking", "Key Delivery", "Vendor Delay", "Parts on Order", "Permit Required", "Other"]
DEFAULT_TASK_ASSIGNEES = {
    "Insp": {"options": ["Michael", "Miguel A"], "default": "Michael"},
    "CB": {"options": ["Make Ready Co"], "default": ""},
    "MRB": {"options": ["Make Ready Co"], "default": "Make Ready Co"},
    "Paint": {"options": ["Roadrunner"], "default": "Roadrunner"},
    "MR": {"options": ["Make Ready Co"], "default": "Make Ready Co"},
    "HK": {"options": ["Brad"], "default": "Brad"},
    "CC": {"options": ["Brad"], "default": ""},
    "FW": {"options": ["Michael", "Miguel A"], "default": ""},
    "QC": {"options": ["Michael", "Miguel A", "Brad"], "default": "Michael"},
}
DEFAULT_TASK_OFFSETS = {
    "Insp": 1,
    "CB": 2,
    "MRB": 3,
    "Paint": 4,
    "MR": 5,
    "HK": 6,
    "CC": 7,
    "FW": 8,
    "QC": 9,
}
OFFSET_OPTIONS = list(range(1, 31))
TASK_TYPES_ALL = ["Insp", "CB", "MRB", "Paint", "MR", "HK", "CC", "FW", "QC"]
TASK_DISPLAY_NAMES = {
    "Insp": "Inspection",
    "CB": "Carpet Bid",
    "MRB": "Make Ready Bid",
    "Paint": "Paint",
    "MR": "Make Ready",
    "HK": "Housekeeping",
    "CC": "Carpet Clean",
    "FW": "Final Walk",
    "QC": "Quality Control",
}
EXEC_LABEL_TO_VALUE = {
    "": None,
    "Not Started": "NOT_STARTED",
    "Scheduled": "SCHEDULED",
    "In Progress": "IN_PROGRESS",
    "Done": "VENDOR_COMPLETED",
    "N/A": "NA",
    "Canceled": "CANCELED",
}
EXEC_VALUE_TO_LABEL = {v: k for k, v in EXEC_LABEL_TO_VALUE.items() if v is not None}
EXEC_VALUE_TO_LABEL[None] = ""
CONFIRM_LABEL_TO_VALUE = {"Pending": "PENDING", "Confirmed": "CONFIRMED", "Rejected": "REJECTED", "Waived": "WAIVED"}
CONFIRM_VALUE_TO_LABEL = {v: k for k, v in CONFIRM_LABEL_TO_VALUE.items()}
BRIDGE_MAP = {
    "All": None,
    "Insp Breach": "inspection_sla_breach",
    "SLA Breach": "sla_breach",
    "SLA MI Breach": "sla_movein_breach",
    "Plan Bridge": "plan_breach",
}


def default_dropdown_config() -> dict:
    return {
        "task_assignees": copy.deepcopy(DEFAULT_TASK_ASSIGNEES),
        "task_offsets": copy.deepcopy(DEFAULT_TASK_OFFSETS),
    }
