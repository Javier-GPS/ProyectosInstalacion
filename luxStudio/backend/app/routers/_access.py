from ..models import Project, User


def can_access_project(project: Project, user: User) -> bool:
    return user.role == "ADMIN" or project.owner_user_id == user.id
