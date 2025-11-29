# flake8: noqa

if __import__("typing").TYPE_CHECKING:
    # import apis into api package
    from schemas.listrr.api.list_api import ListApi

else:
    from lazy_imports import LazyModule, as_package, load

    load(
        LazyModule(
            *as_package(__file__),
            """# import apis into api package
from schemas.listrr.api.list_api import ListApi

""",
            name=__name__,
            doc=__doc__,
        )
    )
