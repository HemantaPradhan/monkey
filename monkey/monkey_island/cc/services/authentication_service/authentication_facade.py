from flask_security import UserDatastore

from monkey_island.cc.event_queue import IIslandEventQueue, IslandEventTopic
from monkey_island.cc.models import IslandMode
from monkey_island.cc.server_utils.encryption import ILockableEncryptor

from .account_role import AccountRole
from .user import User


class AuthenticationFacade:
    """
    A service for user authentication
    """

    def __init__(
        self,
        repository_encryptor: ILockableEncryptor,
        island_event_queue: IIslandEventQueue,
        user_datastore: UserDatastore,
    ):
        self._repository_encryptor = repository_encryptor
        self._island_event_queue = island_event_queue
        self._datastore = user_datastore

    def needs_registration(self) -> bool:
        """
        Checks if a user is already registered on the Island

        :return: Whether registration is required on the Island
        """
        return not User.objects.first()

    def revoke_all_tokens_for_user(self, user: User):
        """
        Revokes all tokens for a specific user
        """
        self._datastore.set_uniquifier(user)

    def revoke_all_tokens_for_island_role_users(self):
        """
        Revokes all tokens for users which have the ISLAND_INTERFACE role
        """
        island_role = self._datastore.find_or_create_role(name=AccountRole.ISLAND_INTERFACE.name)
        for user in User.objects:
            if island_role in user.roles:
                self.revoke_all_tokens_for_user(user)

    def handle_successful_registration(self, username: str, password: str):
        self._reset_island_data()
        self._reset_repository_encryptor(username, password)

    def _reset_island_data(self):
        """
        Resets the island
        """
        self._island_event_queue.publish(IslandEventTopic.CLEAR_SIMULATION_DATA)
        self._island_event_queue.publish(IslandEventTopic.RESET_AGENT_CONFIGURATION)
        self._island_event_queue.publish(
            topic=IslandEventTopic.SET_ISLAND_MODE, mode=IslandMode.UNSET
        )

    def _reset_repository_encryptor(self, username: str, password: str):
        secret = _get_secret_from_credentials(username, password)
        self._repository_encryptor.reset_key()
        self._repository_encryptor.unlock(secret.encode())

    def handle_successful_login(self, username: str, password: str):
        self._unlock_repository_encryptor(username, password)

    def _unlock_repository_encryptor(self, username: str, password: str):
        secret = _get_secret_from_credentials(username, password)
        self._repository_encryptor.unlock(secret.encode())


def _get_secret_from_credentials(username: str, password: str) -> str:
    return f"{username}:{password}"
