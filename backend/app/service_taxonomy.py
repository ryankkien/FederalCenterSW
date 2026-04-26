from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class PscFamily:
    code: str
    label: str
    service: bool = True


PSC_SERVICE_FAMILIES: Dict[str, PscFamily] = {
    "A": PscFamily("A", "Research & Development"),
    "B": PscFamily("B", "Special Studies & Analysis"),
    "C": PscFamily("C", "Architect & Engineering Services"),
    "D": PscFamily("D", "IT & Telecommunications Services"),
    "E": PscFamily("E", "Purchase of Structures & Facilities"),
    "F": PscFamily("F", "Natural Resources & Conservation Services"),
    "G": PscFamily("G", "Social Services"),
    "H": PscFamily("H", "Quality Control, Testing & Inspection"),
    "J": PscFamily("J", "Maintenance, Repair & Rebuilding of Equipment"),
    "K": PscFamily("K", "Modification of Equipment"),
    "L": PscFamily("L", "Technical Representative Services"),
    "M": PscFamily("M", "Operation of Government-Owned Facilities"),
    "N": PscFamily("N", "Installation of Equipment"),
    "P": PscFamily("P", "Salvage Services"),
    "Q": PscFamily("Q", "Medical Services"),
    "R": PscFamily("R", "Professional, Administrative & Management Support Services"),
    "S": PscFamily("S", "Utilities & Housekeeping Services"),
    "T": PscFamily("T", "Photographic, Mapping, Printing & Publication Services"),
    "U": PscFamily("U", "Education & Training Services"),
    "V": PscFamily("V", "Transportation, Travel & Relocation Services"),
    "W": PscFamily("W", "Lease or Rental of Equipment"),
    "X": PscFamily("X", "Lease or Rental of Facilities"),
    "Y": PscFamily("Y", "Construction of Structures & Facilities"),
    "Z": PscFamily("Z", "Maintenance, Repair, or Alteration of Real Property"),
}


def psc_family(psc_code: object) -> Optional[PscFamily]:
    value = str(psc_code or "").strip().upper()
    if not value:
        return None
    return PSC_SERVICE_FAMILIES.get(value[0])


def is_service_psc(psc_code: object) -> bool:
    family = psc_family(psc_code)
    return bool(family and family.service)
