"""The provisioner (prompt 09 §4, contract §18.8): code, not an agent.

It executes a server plan the owner SEALED, exactly, against the Hetzner Cloud
API, and touches only what it made (label managed-by=coinepro-hq). It never
deletes or rebuilds anything, never makes a root password, never SSHes into a
server, and reaches nothing but the api's internal endpoints, OpenBao (its own
read-only AppRole) and api.hetzner.cloud (through egress's provisioner proxy).
"""

__version__ = "0.1.0"
