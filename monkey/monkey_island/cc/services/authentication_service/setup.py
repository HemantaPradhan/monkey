from pathlib import Path

from flask_security import UserDatastore

from common import DIContainer
from monkey_island.cc.event_queue import IIslandEventQueue
from monkey_island.cc.server_utils.encryption import ILockableEncryptor

from . import register_resources
from .account_role import AccountRole
from .authentication_facade import AuthenticationFacade
from .configure_flask_security import configure_flask_security
from .user import User


def setup_authentication(app, api, data_dir: Path, container: DIContainer):
    datastore = configure_flask_security(app, data_dir)
    authentication_facade = _build_authentication_facade(container, datastore)
    register_resources(api, authentication_facade)
    # revoke all old tokens so that the user has to log in again on startup
    _revoke_old_tokens(datastore, authentication_facade)


def _build_authentication_facade(container: DIContainer, user_datastore: UserDatastore):
    repository_encryptor = container.resolve(ILockableEncryptor)
    island_event_queue = container.resolve(IIslandEventQueue)
    return AuthenticationFacade(repository_encryptor, island_event_queue, user_datastore)


def _revoke_old_tokens(user_datastore: UserDatastore, authentication_facade: AuthenticationFacade):
    island_role = user_datastore.find_or_create_role(name=AccountRole.ISLAND_INTERFACE.name)
    for user in User.objects:
        if island_role in user.roles:
            authentication_facade.revoke_all_user_tokens(user)
