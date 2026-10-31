"""Indian number formatting (lakh / crore grouping)."""


def inr(a, d=2):
    """12345678.5 -> '₹1,23,45,678.50'"""
    neg, a = a < 0, abs(a)
    s = "%.*f" % (d, a)
    ip, _, fp = s.partition(".")
    if len(ip) > 3:
        head, tail = ip[:-3], ip[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        ip = ",".join(parts) + "," + tail
    return ("-" if neg else "") + "₹" + ip + ("." + fp if d else "")
