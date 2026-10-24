# Brief: components as frozen pydantic models

**Status: built** with A1, B1 (`Package(comments=)`), C2, D and E as recommended; `CHANGELOG.md` lists the changes.

texpkg (its plan, V21–V27) stores each document with its defaults written out and marked as defaults. To do that it has
to know which fields the author set, for every tree, including one built directly in Python. pydantic's `model_fields_set`
records this; a stdlib dataclass does not. texpkg's V25 decides that texmodel's `Command`, `Environment` and `Passthrough`
become frozen `pydantic.BaseModel`s. This brief says how, what it costs, and what is still open. It reverses the §21 row
"component classes stay stdlib frozen dataclasses" and the §22 "Pydantic coupling" mitigation.

A prototype is in the session scratchpad (not in the repo). It was run against the real `Text`, `Raw` and `Length` types
with pydantic 2.14 and pyright strict. The findings below come from it.

## Recommendation

Switch `Command`, `Environment` and `Passthrough` to frozen pydantic models. Keep how they are built and checked today:
constructing a node in Python does no validation and no coercion, `validate()` stays the one checker of a Python tree
(E2: it reports every broken rule at once), and pydantic validates only data (`from_dict`, texpkg's `load`). Leave `Value`
and `Comment` as they are.

### 1. Positional construction

A `BaseModel`'s `__init__` takes keywords only. The prototype keeps positional construction without a custom `__init__`.
**The metaclass's `__call__` maps the positional arguments**: a command's go to its required fields in order, an
environment's become `content`. Unknown keywords and extra positional arguments raise `TypeError`, as they do today. The
metaclass then calls `cls.model_construct(**given)`. This fills in the defaults and sets `model_fields_set` to exactly the
keys the caller passed.

- **pyright.** `Command` keeps its own `@dataclass_transform(frozen_default=True, kw_only_default=False,
  field_specifiers=(pydantic.Field, field, arg))`, and pyright reads that instead of the kw-only transform on pydantic's
  metaclass. The synthesized `__init__` is `(text: str, *, label: str | None = None, ...)`. It flags a wrong argument
  type, an unknown keyword, and an optional field passed positionally. `arg()` and `field()` return
  `pydantic.Field(kw_only=True, ...)`, and pyright honours that, so the rule "optional fields are written
  `arg(default=...)`" does not change. The metaclass's `__call__` has no return annotation, so pyright evaluates
  `__init__`.
- **Environments.** They keep `__init__(self, *content: Node, **args: object)`, now declared under `if TYPE_CHECKING:`
  only. A runtime `__init__` would make pydantic treat it as a custom init, and `model_validate` would then call it with
  the data (the prototype's first version lost `Raw` coercion from data this way). An environment's keywords stay
  unchecked by pyright, as they are today: `dataclass_transform` cannot describe `*content`.
- **Not taken:**
  - a custom `__init__`: it disables validation from data, as described above;
  - pydantic's validating `__init__`: see 2;
  - dropping positional children: every document and example would change, for nothing the metaclass cannot do.

### 2. What changes in behaviour

- **Validation and coercion.** A Python tree stays unvalidated: `Fact(None)` builds and `validate()` reports `TM-C003`, so
  the tests that build invalid nodes keep passing. Data is validated and coerced (a `str` becomes a `Raw`), which already
  happens today through the mirror models. Validating at construction instead would raise one pydantic error per node,
  the first one Python hits, and would break E2.
- **Equality and hashing.** Both are structural, as with dataclasses. Equality ignores `model_fields_set`, so
  `Slot("x") == Slot("x", label=None)` (checked in the prototype). That is the right equality for trees (the same render),
  but texpkg cannot compare trees to find out whether an author set a field. It must read `model_fields_set`.
- **`repr`.** `_Node.__repr__` stays `_repr`. `__str__` has to be overridden too: pydantic's `__str__` is `text='x'
  label=None`, while today `str(node)` is the constructor expression.
- **Frozen.** Assigning to a field raises `pydantic.ValidationError` instead of `dataclasses.FrozenInstanceError` (no
  component test asserts the old one).
- **`_Meta` and `_build`.** `_Meta` becomes a subclass of pydantic's `ModelMetaclass` (still giving `.times`, now also
  `__call__`). `_build` moves from `__init_subclass__` to `__pydantic_init_subclass__`, which runs after pydantic has
  collected the fields. `abstract=` and `unused=` still reach it as class keywords (checked). `_arguments` reads
  `cls.model_fields` (`FieldInfo.default`, `PydanticUndefined`, `json_schema_extra` or metadata for `ArgOptions`,
  `renamed_from`, `doc`, `meta`) instead of `dataclasses.fields`. The field order is the same.
- **Class attributes.** pydantic refuses an unannotated class attribute, for example `body = r"..."`. `_Node` must
  declare `body`, `begin`, `end`, `children`, `cs`, `syntax`, `defined_by` and `meta` as `ClassVar` (most already are).
  A subclass assigning one is then accepted, and a `body` method is ignored (checked).
- **New declaration errors.** A field cannot shadow a `BaseModel` attribute (`copy`, `json`, `dict`, `schema`,
  `construct`, ...) or start with `model_`. pydantic only warns about these, so texmodel should refuse them with a
  `TM-M045` that names the field, like `type` (`TM-M030`).
- **`validate()`** overrides `BaseModel.validate`, pydantic v1's deprecated classmethod. pyright strict reports
  `reportIncompatibleMethodOverride`. **Open choice A** (below).
- **`Package._make` / `make_command`.** These build a class from data. The field specs become `FieldInfo`, and
  `_field_data` compares `default` and `json_schema_extra` instead of `dataclasses.Field.metadata`. TM-M007's meaning
  does not change.

### 3. What it removes from `spec`

- **`from_dict` for a command.** It is already `TypeAdapter(cls).validate_python` over the dataclass, and becomes
  `cls.model_validate`.
- **`_model`, `_MODELS`, `_node`, `_comment_model`.** These go only if an environment's `content` field has a static,
  grammar-derived type: a discriminated union (`"type"`) of its `children` kinds and `Comment`. The metaclass can write
  that annotation from `children` before pydantic builds the class, since the kinds already exist.
  - **What blocks it.** `from_dict(..., comments=[...])` adds comment classes at call time. A before-validator on the
    content items could turn those into instances from the validation context, at the cost of flat error paths inside a
    comment. **Open choice B**.
  - **Until B is settled,** `_model` stays for environments only, and `_node` must pass `model_fields_set`, not every
    field. Otherwise a loaded document would look as if the author had set every field.
- **`to_dict`.** It becomes a model dump with `"type"` added by a wrap serializer, and the per-value `TypeAdapter(...)`
  with `exclude_defaults=True` goes. **Open choice C**: what `to_dict` leaves out.
- **`json_schema`.** It becomes `cls.model_json_schema()` plus `_annotate`. The `x-renamed-from`, `doc` and `meta`
  post-processing stays, unless `arg`/`field` write them as `json_schema_extra`, which is simpler and moves them onto the
  field.

### 4. Goldens, pyright, performance

- **Generated output: no change.** Rendering reads `__tm_args__`, which `_arguments` still builds in the same order with
  the same defaults. No `.sty`, `.tex` or plan golden includes `to_dict` output. Proof: the golden tests and the `tex`
  suite pass unchanged, with no `UPDATE_GOLDEN`.
- **pyright strict.** As described in 1, with one new narrow ignore (or none, under A1). `spec` gets simpler to type:
  fewer `create_model` casts and fewer `Any`.
- **Performance.** On the prototype, 20 000 `Slot(...)` nodes take:

  | how they are built | time |
  |---|---|
  | dataclass (today) | 6.6 ms |
  | pydantic, validating `__init__` | 32 ms |
  | `model_construct` (recommended) | 100 ms |

  That is about 5 µs a node, roughly 15 times slower. A 200-card deck of about 2 000 nodes builds in about 10 ms, and
  compiling dominates by orders of magnitude. Building an environment of 20 000 children takes 0.2 ms, and hashing it
  3.8 ms. If construction ever matters, a hand-written equivalent of `model_construct` that sets `__dict__` and
  `__pydantic_fields_set__` directly is about as fast as the validating path. It uses pydantic's private slots, so it is
  not proposed now.

### 5. Migration plan

These steps are one change, since the components cannot be half-switched:

1. `components.py`: `_Meta(ModelMetaclass)` with `__call__`, the `_Node` config (`frozen=True`), `_build` in
   `__pydantic_init_subclass__`, `_arguments` over `model_fields`, the `ClassVar` declarations, `__str__`, and `TM-M045`.
   `Environment` gets the `TYPE_CHECKING`-only `__init__`. `Passthrough` becomes a model with `tex: Raw`.
2. `interface.arg` and `components.field`: return `pydantic.Field(kw_only=True, ...)` with the texmodel options in
   `json_schema_extra` or metadata.
3. `package.py`: `_make` and `_field_data` work on `FieldInfo`.
4. `spec.py`: commands go direct. Environments either keep `_model` with `_node` fixed to `model_fields_set`, or drop it,
   depending on B. `to_dict` follows C.
5. Docs: the plan's §5 D1 ("nodes are frozen pydantic models") and §17. Replace the §21 row: "Components are frozen
   pydantic models: construction maps positional arguments in the metaclass and does not validate (`validate()` does);
   data is validated by pydantic; `model_fields_set` is what the caller passed." Rewrite the §22 "Pydantic coupling"
   risk: pydantic is the component base, and the mitigation is that only `components` and `spec` touch its API.
   README: the component section. `docs/known-limitations.md`: environment keywords are unchecked by pyright.

**Tests that prove it.** Each fails without the change:

- `model_fields_set` for a positional and a keyword argument, for an explicit default (`label=None` is set), for an
  environment's arguments (with `content` excluded or always set, per D), and after `from_dict` (only the keys in the
  data).
- A hypothesis law: `from_dict(to_dict(node))` keeps both the tree and its `model_fields_set` (under C2).
- `Fact(None)` builds and `validate()` gives `TM-C003`, while `from_dict` of the same data gives `TM-C020`.
- An unknown keyword or an extra positional argument raises `TypeError`, and an optional field passed positionally
  raises `TypeError`.
- `str(node) == repr(node)`. Equality and hashing ignore `model_fields_set`.
- `TM-M045` for a field named `json`, and for one named `model_x`.
- A pyright fixture in the style of the existing typing tests: a positional required argument passes; an optional
  argument passed positionally, a wrong type and an unknown keyword each fail.
- The goldens, `test_examples.py` and the `tex` suite, unchanged.

**CHANGELOG (`[Unreleased]`).**

- **Changed:**
  - `Command`, `Environment` and `Passthrough` are frozen pydantic models; `model_fields_set` holds the fields the caller
    passed, positionally or by keyword.
  - Assigning to a node's field raises `pydantic.ValidationError`.
  - `arg()` and `field()` return pydantic `FieldInfo`.
  - `to_dict` per C.
  - `validate()` per A.
- **Removed:** `texmodel.spec`'s generated mirror models, if B allows.
- **Added:** `TM-M045`, a field that shadows a pydantic attribute.
- **No generated output changes.**

## Choices

Decided by the maintainer: **A1, C2, D (keep `content` in the set, documented), E (leave `Value` and `Comment`)**. B is open.

- **A. `validate()`.**
  - **A1 (recommended):** rename it to `violations()`. It is a public API change, but the name says what it returns, and
    no ignore is needed.
  - **A2:** keep it, with `# pyright: ignore[reportIncompatibleMethodOverride]` and the reason that pydantic's
    `validate` is v1's deprecated classmethod.
- **B. Comment classes in data.** Today a grammar cannot name a comment: `_grammar` accepts components only (a `Comment`
  kind in `children` is `TM-M020`), any comment may stand anywhere in a Python tree and the grammar check skips it (B3),
  and data learns of subclasses only through `from_dict(comments=)`.
  - **B1 (recommended):** declare them once on the package (§21a 18), `Package(..., comments=[CardHeader])`: data
    accepts the plain `Comment` and the package's comment classes in every environment, as a Python tree already does.
    Then every environment's `content` type is static and the mirror models go. Listing comments in a grammar
    (`Anywhere(CardHeader)`) is the other form, but it would refuse an unlisted comment that a Python tree accepts today.
  - **B2:** keep `from_dict(comments=)` and `_model` for environments.
  - **B3:** use a validation context, with flat error paths inside a comment.
- **C. What `to_dict` leaves out.**
  - **C1:** keep today's rule: `None` and `False` are left out, everything else is written.
  - **C2 (recommended):** `exclude_unset`, which writes what the caller set. A round trip then keeps
    `model_fields_set`, and it is what texpkg's mark is built on. A value the author set to its default is written; a
    default the author left is not.
- **D. `content` in `model_fields_set`.** It is always passed, so it is always in the set. Either document that, or have
  `__call__` leave it out when it is empty.
  - **Recommended:** keep it in and document it. texpkg marks defaults of arguments only.
- **E. `Value`.** It is a single setting that is always given (`FactGap(Length("3mm"))`), so it has nothing to mark.
  Making it a model clashes with its class-level `default` (pydantic would read the annotated `default: T` as a field,
  and pyright refuses a `ClassVar[T]`).
  - **Recommended:** leave it out of this change. Add `__eq__` and `__hash__` if texpkg needs to compare settings (today
    two equal settings are not `==`).

## Alternative considered

Without pydantic, about 20 lines would do it: `_Node` records the given names in an `__init__` (`Environment` already has
one) as a `fields_set` property. That costs nothing in speed and adds no coupling. V25 decided against it, because texpkg
wants the components themselves to be pydantic models for its stored state, its two schemas and its serializer hooks
(V26, V27). That reason stands only if texpkg uses those hooks on the components; if it keeps its own state models, this
alternative is enough.
