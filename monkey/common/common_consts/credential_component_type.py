from enum import Enum


class CredentialComponentType(Enum):
    USERNAME = "username"
    PASSWORD = "password"
    NT_HASH = "nt_hash"
    LM_HASH = "lm_hash"
    SSH_KEYPAIR = "ssh_keypair"
