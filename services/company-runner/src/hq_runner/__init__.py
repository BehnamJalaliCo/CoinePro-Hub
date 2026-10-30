"""hq-runner: the holding's job runner on a company server (contract §26).

It opens outbound HTTPS to the hub only, long-polls for jobs, runs them as the
server's work user and streams their events back. Nothing listens on any port.
"""

__version__ = "0.1.0"
