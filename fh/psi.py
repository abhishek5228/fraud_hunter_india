"""Private set intersection for cross-bank mule sharing (DDH-based, standard library only).

Why this exists: the keyed-hash feed in consortium.py lets anyone holding the shared key test guesses (phone numbers and UPI IDs have
little entropy). Here there is no shared key. Each bank has its own secret exponent, and a bank can learn whether ONE OF ITS OWN
payees is on the other bank's flagged list only by asking that bank to blind the question.

Protocol (A holds a flagged set X, B asks about its own payees Y; H hashes into the prime-order subgroup of a 2048-bit safe-prime group):
  A -> B   blind_A(x) = H(x)^(2a) for every x in X (shuffled)
  B -> A   blind_B(y) = H(y)^(2b) for every y in Y
  A -> B   H(y)^(2b*2a)                       (A re-blinds, never sees y)
  B        computes H(x)^(2a*2b) for A's list and compares.   y is flagged by A  <=>  the values match.
B learns which of ITS OWN payees A flagged, and |X|. A learns |Y|. Nobody learns a payee they did not already hold.
The doubled exponent squares every incoming value, which removes any component outside the prime-order subgroup (small-subgroup safety).

What is still left (read this): B can still ask about as many guessed payees as it likes, so a malicious member could use A as a membership oracle
for guessed phone numbers. The mitigations here are a size cap per query, a per-hour query budget and an audit entry; they raise the cost,
they do not remove it. Group: RFC 3526 group 14 (verified as a safe prime). No claim is made that this is production-audited cryptography.
"""
import hashlib
import os
import random
import secrets

P = int("FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74020BBEA63B139B22514A08798E3404DDEF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7EDEE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3DC2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F83655D23DCA3AD961C62F356208552BB9ED529077096966D670C354E4ABC9804F1746C08CA18217C32905E462E36CE3BE39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9DE2BCBF6955817183995497CEA956AE515D2261898FA051015728E5A8AACAA68FFFFFFFFFFFFFFFF", 16)
Q = (P - 1) // 2
W = 512                      # hex digits per element
MAX_QUERY = 10000


def norm(x):
    return str(x).strip().lower().encode()


def h2g(item):
    """Hash an identifier into the order-Q subgroup (squaring a uniform value mod P)."""
    d = b"".join(hashlib.sha512(b"fh-psi-v1|%d|" % i + norm(item)).digest() for i in range(5))
    x = int.from_bytes(d, "big") % P
    return pow(x if x > 1 else 2, 2, P)


def _hex(n):
    return "%0*x" % (W, n)


def _parse(h):
    if not isinstance(h, str) or len(h) != W:
        raise ValueError("bad element")
    n = int(h, 16)
    if not 1 < n < P - 1:
        raise ValueError("element out of range")
    return n


class Party:
    def __init__(self, secret=None):
        self.s = secret or (secrets.randbits(255) | (1 << 254))      # 255-bit secret exponent
        self.e = 2 * self.s

    @classmethod
    def load(cls, path=None):
        """Secret from FH_PSI_SECRET, else a 0600 file next to the model (created on first use)."""
        env = os.environ.get("FH_PSI_SECRET")
        if env:
            return cls(int(env, 16))
        if path and os.path.exists(path):
            return cls(int(open(path).read().strip(), 16))
        p = cls()
        if path:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write("%x" % p.s)
        return p

    def blind(self, items):
        return [_hex(pow(h2g(i), self.e, P)) for i in items]

    def reblind(self, hexes):
        if len(hexes) > MAX_QUERY:
            raise ValueError("query too large (max %d)" % MAX_QUERY)
        return [_hex(pow(_parse(h), self.e, P)) for h in hexes]

    def published_set(self, items):
        out = self.blind(set(items))
        random.SystemRandom().shuffle(out)                         # order must not reveal which item is which
        return out


def find_matches(me, mine, peer_set, reblinded):
    """B side. mine: my payee ids (same order as the queries I sent); reblinded: A's answers; peer_set: A's published list."""
    doubled = {_hex(pow(_parse(h), me.e, P)) for h in peer_set}
    return [m for m, r in zip(mine, reblinded) if r in doubled]


def sync(me, mine, get_set, reblind_remote):
    """Run the whole protocol from B's side. get_set() -> list of hex; reblind_remote(list_of_hex) -> list of hex."""
    mine = sorted(set(mine))[:MAX_QUERY]
    if not mine:
        return []
    peer_set = get_set()
    queries = me.blind(mine)
    answers = reblind_remote(queries)
    if len(answers) != len(queries):
        raise ValueError("peer answered the wrong number of queries")
    return find_matches(me, mine, peer_set, answers)
