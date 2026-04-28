import re
from datetime import datetime


NGINX_ACCESS_LOG_PATTERN = re.compile(
    r'^(?P<source_ip>\S+) '
    r'(?P<ident>\S+) '
    r'(?P<authuser>\S+) '
    r'\[(?P<timestamp>[^\]]+)\] '
    r'"(?P<method>[A-Z]+) (?P<path>\S+)(?: (?P<protocol>[^"]+))?" '
    r'(?P<status>\d{3}) '
    r'(?P<body_bytes_sent>\S+)'
    r'(?: "(?P<referer>[^"]*)" "(?P<user_agent>[^"]*)")?$'
)


def parse_nginx_access_log_line(line):
    if not isinstance(line, str) or not line.strip():
        raise ValueError("Log line is required")

    match = NGINX_ACCESS_LOG_PATTERN.match(line.strip())
    if not match:
        raise ValueError("Malformed nginx access log line")

    parsed = match.groupdict()

    try:
        parsed["status"] = int(parsed["status"])
    except (TypeError, ValueError) as error:
        raise ValueError("Invalid HTTP status in log line") from error

    bytes_value = parsed.get("body_bytes_sent")
    if bytes_value == "-":
        parsed["body_bytes_sent"] = None
    else:
        try:
            parsed["body_bytes_sent"] = int(bytes_value)
        except (TypeError, ValueError) as error:
            raise ValueError("Invalid body bytes value in log line") from error

    timestamp_value = parsed.get("timestamp")
    if timestamp_value:
        try:
            parsed["event_timestamp"] = datetime.strptime(timestamp_value, "%d/%b/%Y:%H:%M:%S %z").isoformat()
        except ValueError:
            parsed["event_timestamp"] = None
    else:
        parsed["event_timestamp"] = None

    return parsed
