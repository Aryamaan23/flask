from collections import defaultdict
from functools import update_wrapper

from .scaffold import _endpoint_from_view_func
from .scaffold import _sentinel
from .scaffold import Scaffold


class BlueprintSetupState:
    """Temporary holder object for registering a blueprint with the
    application.  An instance of this class is created by the
    :meth:`~flask.Blueprint.make_setup_state` method and later passed
    to all register callback functions.
    """

    def __init__(self, blueprint, app, options, first_registration):
        #: a reference to the current application
        self.app = app

        #: a reference to the blueprint that created this setup state.
        self.blueprint = blueprint

        #: a dictionary with all options that were passed to the
        #: :meth:`~flask.Flask.register_blueprint` method.
        self.options = options

        #: as blueprints can be registered multiple times with the
        #: application and not everything wants to be registered
        #: multiple times on it, this attribute can be used to figure
        #: out if the blueprint was registered in the past already.
        self.first_registration = first_registration

        subdomain = self.options.get("subdomain")
        if subdomain is None:
            subdomain = self.blueprint.subdomain

        #: The subdomain that the blueprint should be active for, ``None``
        #: otherwise.
        self.subdomain = subdomain

        url_prefix = self.options.get("url_prefix")
        if url_prefix is None:
            url_prefix = self.blueprint.url_prefix
        #: The prefix that should be used for all URLs defined on the
        #: blueprint.
        self.url_prefix = url_prefix

        #: A dictionary with URL defaults that is added to each and every
        #: URL that was defined with the blueprint.
        self.url_defaults = dict(self.blueprint.url_values_defaults)
        self.url_defaults.update(self.options.get("url_defaults", ()))

    def add_url_rule(self, rule, endpoint=None, view_func=None, **options):
        """A helper method to register a rule (and optionally a view function)
        to the application.  The endpoint is automatically prefixed with the
        blueprint's name.
        """
        if self.url_prefix is not None:
            if rule:
                rule = "/".join((self.url_prefix.rstrip("/"), rule.lstrip("/")))
            else:
                rule = self.url_prefix
        options.setdefault("subdomain", self.subdomain)
        if endpoint is None:
            endpoint = _endpoint_from_view_func(view_func)
        defaults = self.url_defaults
        if "defaults" in options:
            defaults = dict(defaults, **options.pop("defaults"))
        self.app.add_url_rule(
            rule,
            f"{self.blueprint.name}.{endpoint}",
            view_func,
            defaults=defaults,
            **options,
        )


class Blueprint(Scaffold):
    """Represents a blueprint, a collection of routes and other
    app-related functions that can be registered on a real application
    later.

    A blueprint is an object that allows defining application functions
    without requiring an application object ahead of time. It uses the
    same decorators as :class:`~flask.Flask`, but defers the need for an
    application by recording them for later registration.

    Decorating a function with a blueprint creates a deferred function
    that is called with :class:`~flask.blueprints.BlueprintSetupState`
    when the blueprint is registered on an application.

    See :doc:`/blueprints` for more information.

    :param name: The name of the blueprint. Will be prepended to each
        endpoint name.
    :param import_name: The name of the blueprint package, usually
        ``__name__``. This helps locate the ``root_path`` for the
        blueprint.
    :param static_folder: A folder with static files that should be
        served by the blueprint's static route. The path is relative to
        the blueprint's root path. Blueprint static files are disabled
        by default.
    :param static_url_path: The url to serve static files from.
        Defaults to ``static_folder``. If the blueprint does not have
        a ``url_prefix``, the app's static route will take precedence,
        and the blueprint's static files won't be accessible.
    :param template_folder: A folder with templates that should be added
        to the app's template search path. The path is relative to the
        blueprint's root path. Blueprint templates are disabled by
        default. Blueprint templates have a lower precedence than those
        in the app's templates folder.
    :param url_prefix: A path to prepend to all of the blueprint's URLs,
        to make them distinct from the rest of the app's routes.
    :param subdomain: A subdomain that blueprint routes will match on by
        default.
    :param url_defaults: A dict of default values that blueprint routes
        will receive by default.
    :param root_path: By default, the blueprint will automatically set
        this based on ``import_name``. In certain situations this
        automatic detection can fail, so the path can be specified
        manually instead.

    .. versionchanged:: 1.1.0
        Blueprints have a ``cli`` group to register nested CLI commands.
        The ``cli_group`` parameter controls the name of the group under
        the ``flask`` command.

    .. versionadded:: 0.7
    """

    warn_on_modifications = False
    _got_registered_once = False

    #: Blueprint local JSON encoder class to use. Set to ``None`` to use
    #: the app's :class:`~flask.Flask.json_encoder`.
    json_encoder = None
    #: Blueprint local JSON decoder class to use. Set to ``None`` to use
    #: the app's :class:`~flask.Flask.json_decoder`.
    json_decoder = None

    def __init__(
        self,
        name,
        import_name,
        static_folder=None,
        static_url_path=None,
        template_folder=None,
        url_prefix=None,
        subdomain=None,
        url_defaults=None,
        root_path=None,
        cli_group=_sentinel,
    ):
        super().__init__(
            import_name=import_name,
            static_folder=static_folder,
            static_url_path=static_url_path,
            template_folder=template_folder,
            root_path=root_path,
        )
        self.name = name
        self.url_prefix = url_prefix
        self.subdomain = subdomain
        self.deferred_functions = []

        if url_defaults is None:
            url_defaults = {}

        self.url_values_defaults = url_defaults
        self.cli_group = cli_group

    def _is_setup_finished(self):
        return self.warn_on_modifications and self._got_registered_once

    def record(self, func):
        """Registers a function that is called when the blueprint is
        registered on the application.  This function is called with the
        state as argument as returned by the :meth:`make_setup_state`
        method.
        """
        if self._got_registered_once and self.warn_on_modifications:
            from warnings import warn

            warn(
                Warning(
                    "The blueprint was already registered once but is"
                    " getting modified now. These changes will not show"
                    " up."
                )
            )
        self.deferred_functions.append(func)

    def record_once(self, func):
        """Works like :meth:`record` but wraps the function in another
        function that will ensure the function is only called once.  If the
        blueprint is registered a second time on the application, the
        function passed is not called.
        """

        def wrapper(state):
            if state.first_registration:
                func(state)

        return self.record(update_wrapper(wrapper, func))

    def make_setup_state(self, app, options, first_registration=False):
        """Creates an instance of :meth:`~flask.blueprints.BlueprintSetupState`
        object that is later passed to the register callback functions.
        Subclasses can override this to return a subclass of the setup state.
        """
        return BlueprintSetupState(self, app, options, first_registration)

    def register(self, app, options, first_registration=False):
        """Called by :meth:`Flask.register_blueprint` to register all
        views and callbacks registered on the blueprint with the
        application. Creates a :class:`.BlueprintSetupState` and calls
        each :meth:`record` callbackwith it.

        :param app: The application this blueprint is being registered
            with.
        :param options: Keyword arguments forwarded from
            :meth:`~Flask.register_blueprint`.
        :param first_registration: Whether this is the first time this
            blueprint has been registered on the application.
        """
        self._got_registered_once = True
        state = self.make_setup_state(app, options, first_registration)

        if self.has_static_folder:
            state.add_url_rule(
                f"{self.static_url_path}/<path:filename>",
                view_func=self.send_static_file,
                endpoint="static",
            )

        # Merge blueprint data into parent.
        if first_registration:

            def extend(bp_dict, parent_dict, ensure_sync=False):
                for key, values in bp_dict.items():
                    key = self.name if key is None else f"{self.name}.{key}"

                    if ensure_sync:
                        values = [app.ensure_sync(func) for func in values]

                    parent_dict[key].extend(values)

            for key, value in self.error_handler_spec.items():
                key = self.name if key is None else f"{self.name}.{key}"
                value = defaultdict(
                    dict,
                    {
                        code: {
                            exc_class: app.ensure_sync(func)
                            for exc_class, func in code_values.items()
                        }
                        for code, code_values in value.items()
                    },
                )
                app.error_handler_spec[key] = value

            for endpoint, func in self.view_functions.items():
                app.view_functions[endpoint] = app.ensure_sync(func)

            extend(
                self.before_request_funcs, app.before_request_funcs, ensure_sync=True
            )
            extend(self.after_request_funcs, app.after_request_funcs, ensure_sync=True)
            extend(
                self.teardown_request_funcs,
                app.teardown_request_funcs,
                ensure_sync=True,
            )
            extend(self.url_default_functions, app.url_default_functions)
            extend(self.url_value_preprocessors, app.url_value_preprocessors)
            extend(self.template_context_processors, app.template_context_processors)

        for deferred in self.deferred_functions:
            deferred(state)

        if not self.cli.commands:
            return

        cli_resolved_group = options.get("cli_group", self.cli_group)

        if cli_resolved_group is None:
            app.cli.commands.update(self.cli.commands)
        elif cli_resolved_group is _sentinel:
            self.cli.name = self.name
            app.cli.add_command(self.cli)
        else:
            self.cli.name = cli_resolved_group
            app.cli.add_command(self.cli)

    def add_url_rule(self, rule, endpoint=None, view_func=None, **options):
        """Like :meth:`Flask.add_url_rule` but for a blueprint.  The endpoint for
        the :func:`url_for` function is prefixed with the name of the blueprint.
        """
        if endpoint:
            assert "." not in endpoint, "Blueprint endpoints should not contain dots"
        if view_func and hasattr(view_func, "__name__"):
            assert (
                "." not in view_func.__name__
            ), "Blueprint view function name should not contain dots"
        self.record(lambda s: s.add_url_rule(rule, endpoint, view_func, **options))

    def app_template_filter(self, name=None):
        """Register a custom template filter, available application wide.  Like
        :meth:`Flask.template_filter` but for a blueprint.

        :param name: the optional name of the filter, otherwise the
                     function name will be used.
        """

        def decorator(f):
            self.add_app_template_filter(f, name=name)
            return f

        return decorator

    def add_app_template_filter(self, f, name=None):
        """Register a custom template filter, available application wide.  Like
        :meth:`Flask.add_template_filter` but for a blueprint.  Works exactly
        like the :meth:`app_template_filter` decorator.

        :param name: the optional name of the filter, otherwise the
                     function name will be used.
        """

        def register_template(state):
            state.app.jinja_env.filters[name or f.__name__] = f

        self.record_once(register_template)

    def app_template_test(self, name=None):
        """Register a custom template test, available application wide.  Like
        :meth:`Flask.template_test` but for a blueprint.

        .. versionadded:: 0.10

        :param name: the optional name of the test, otherwise the
                     function name will be used.
        """

        def decorator(f):
            self.add_app_template_test(f, name=name)
            return f

        return decorator

    def add_app_template_test(self, f, name=None):
        """Register a custom template test, available application wide.  Like
        :meth:`Flask.add_template_test` but for a blueprint.  Works exactly
        like the :meth:`app_template_test` decorator.

        .. versionadded:: 0.10

        :param name: the optional name of the test, otherwise the
                     function name will be used.
        """

        def register_template(state):
            state.app.jinja_env.tests[name or f.__name__] = f

        self.record_once(register_template)

    def app_template_global(self, name=None):
        """Register a custom template global, available application wide.  Like
        :meth:`Flask.template_global` but for a blueprint.

        .. versionadded:: 0.10

        :param name: the optional name of the global, otherwise the
                     function name will be used.
        """

        def decorator(f):
            self.add_app_template_global(f, name=name)
            return f

        return decorator

    def add_app_template_global(self, f, name=None):
        """Register a custom template global, available application wide.  Like
        :meth:`Flask.add_template_global` but for a blueprint.  Works exactly
        like the :meth:`app_template_global` decorator.

        .. versionadded:: 0.10

        :param name: the optional name of the global, otherwise the
                     function name will be used.
        """

        def register_template(state):
            state.app.jinja_env.globals[name or f.__name__] = f

        self.record_once(register_template)

    def before_app_request(self, f):
        """Like :meth:`Flask.before_request`.  Such a function is executed
        before each request, even if outside of a blueprint.
        """
        self.record_once(
            lambda s: s.app.before_request_funcs.setdefault(None, []).append(
                s.app.ensure_sync(f)
            )
        )
        return f

    def before_app_first_request(self, f):
        """Like :meth:`Flask.before_first_request`.  Such a function is
        executed before the first request to the application.
        """
        self.record_once(
            lambda s: s.app.before_first_request_funcs.append(s.app.ensure_sync(f))
        )
        return f

    def after_app_request(self, f):
        """Like :meth:`Flask.after_request` but for a blueprint.  Such a function
        is executed after each request, even if outside of the blueprint.
        """
        self.record_once(
            lambda s: s.app.after_request_funcs.setdefault(None, []).append(
                s.app.ensure_sync(f)
            )
        )
        return f

    def teardown_app_request(self, f):
        """Like :meth:`Flask.teardown_request` but for a blueprint.  Such a
        function is executed when tearing down each request, even if outside of
        the blueprint.
        """
        self.record_once(
            lambda s: s.app.teardown_request_funcs.setdefault(None, []).append(f)
        )
        return f

    def app_context_processor(self, f):
        """Like :meth:`Flask.context_processor` but for a blueprint.  Such a
        function is executed each request, even if outside of the blueprint.
        """
        self.record_once(
            lambda s: s.app.template_context_processors.setdefault(None, []).append(f)
        )
        return f

    def app_errorhandler(self, code):
        """Like :meth:`Flask.errorhandler` but for a blueprint.  This
        handler is used for all requests, even if outside of the blueprint.
        """

        def decorator(f):
            self.record_once(lambda s: s.app.errorhandler(code)(f))
            return f

        return decorator

    def app_url_value_preprocessor(self, f):
        """Same as :meth:`url_value_preprocessor` but application wide."""
        self.record_once(
            lambda s: s.app.url_value_preprocessors.setdefault(None, []).append(f)
        )
        return f

    def app_url_defaults(self, f):
        """Same as :meth:`url_defaults` but application wide."""
        self.record_once(
            lambda s: s.app.url_default_functions.setdefault(None, []).append(f)
        )
        return f

    def ensure_sync(self, f):
        """Ensure the function is synchronous.

        Override if you would like custom async to sync behaviour in
        this blueprint. Otherwise the app's
        :meth:`~flask.Flask.ensure_sync` is used.

        .. versionadded:: 2.0
        """
        return f
