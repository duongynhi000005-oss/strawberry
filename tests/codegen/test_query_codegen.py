# - 1. test fragments
# - 2. test variables
# - 3. test input objects
# - 4. test mutations (raise?)
# - 5. test subscriptions (raise)

from pathlib import Path

import pytest
from pytest_snapshot.plugin import Snapshot

from strawberry.codegen import QueryCodegen, QueryCodegenPlugin
from strawberry.codegen.exceptions import (
    MultipleOperationsProvidedError,
    NoOperationNameProvidedError,
    NoOperationProvidedError,
)
from strawberry.codegen.plugins.python import PythonPlugin
from strawberry.codegen.plugins.typescript import TypeScriptPlugin

HERE = Path(__file__).parent
QUERIES = list(HERE.glob("queries/*.graphql"))


@pytest.mark.parametrize(
    ("plugin_class", "plugin_name", "extension"),
    [
        (PythonPlugin, "python", "py"),
        (TypeScriptPlugin, "typescript", "ts"),
    ],
    ids=["python", "typescript"],
)
@pytest.mark.parametrize("query", QUERIES, ids=[x.name for x in QUERIES])
def test_codegen(  # noqa: PLR0917
    query: Path,
    plugin_class: type[QueryCodegenPlugin],
    plugin_name: str,
    extension: str,
    snapshot: Snapshot,
    schema,
):
    generator = QueryCodegen(schema, plugins=[plugin_class(query)])

    result = generator.run(query.read_text())

    code = result.to_string()

    snapshot.snapshot_dir = HERE / "snapshots" / plugin_name
    snapshot.assert_match(code, f"{query.with_suffix('').stem}.{extension}")


def test_codegen_fails_if_no_operation_name(schema, tmp_path):
    query = tmp_path / "query.graphql"
    data = "query { hello }"
    with query.open("w") as f:
        f.write(data)

    generator = QueryCodegen(schema, plugins=[PythonPlugin(query)])

    with pytest.raises(NoOperationNameProvidedError):
        generator.run(data)


def test_codegen_fails_if_no_operation(schema, tmp_path):
    query = tmp_path / "query.graphql"
    data = "type X { hello: String }"
    with query.open("w") as f:
        f.write(data)

    generator = QueryCodegen(schema, plugins=[PythonPlugin(query)])

    with pytest.raises(NoOperationProvidedError):
        generator.run(data)


def test_fails_with_multiple_operations(schema, tmp_path):
    query = tmp_path / "query.graphql"
    data = "query { hello } query { world }"
    with query.open("w") as f:
        f.write(data)

    generator = QueryCodegen(schema, plugins=[PythonPlugin(query)])

    with pytest.raises(MultipleOperationsProvidedError):
        generator.run(data)


@pytest.mark.parametrize("plugin_class", [PythonPlugin, TypeScriptPlugin])
def test_nested_fragment_spread_does_not_depend_on_definition_order(
    plugin_class: type[QueryCodegenPlugin], schema, tmp_path
):
    operation = "query OperationName { listLife { ...LifeFields } }"
    life_fields = (
        "fragment LifeFields on PersonAnimalLifeContainer"
        " { items1 { ...PersonFields } }"
    )
    person_fields = "fragment PersonFields on Person { name age }"
    query = tmp_path / "query.graphql"

    def generate(document: str) -> str:
        generator = QueryCodegen(schema, plugins=[plugin_class(query)])
        return generator.run(document).to_string()

    inner_first = generate(f"{operation}\n{person_fields}\n{life_fields}")
    inner_last = generate(f"{operation}\n{life_fields}\n{person_fields}")

    assert inner_last == inner_first
    assert "PersonFields" in inner_last


def test_codegen_emits_descriptions_as_docstrings(tmp_path):
    import ast

    import strawberry
    from strawberry.codegen import QueryCodegen
    from strawberry.codegen.plugins.python import PythonPlugin

    @strawberry.type(description="A tracked issue.")
    class Issue:
        id: strawberry.ID = strawberry.field(description="Unique identifier.")
        title: str = strawberry.field(description="The issue title.")

    @strawberry.input(description="Fields for a new issue.")
    class IssueCreateInput:
        title: str = strawberry.field(description="Title for the new issue.")

    @strawberry.type
    class Query:
        @strawberry.field
        def issue(self, id: strawberry.ID) -> Issue:
            return Issue(id=id, title="")

    @strawberry.type
    class Mutation:
        @strawberry.mutation
        def issue_create(self, input: IssueCreateInput) -> Issue:
            return Issue(id="1", title=input.title)

    schema = strawberry.Schema(query=Query, mutation=Mutation)
    query_str = """
    mutation Create($input: IssueCreateInput!) {
      issueCreate(input: $input) { id title }
    }
    """
    query_file = tmp_path / "create.graphql"
    generator = QueryCodegen(schema, plugins=[PythonPlugin(query_file)])
    result = generator.run(query_str)
    code = result.to_string()

    assert '"""A tracked issue."""' in code
    assert '"""Unique identifier."""' in code
    assert '"""The issue title."""' in code
    assert '"""Fields for a new issue."""' in code
    assert '"""Title for the new issue."""' in code

    ast.parse(code)


def test_codegen_docstrings_with_quotes_and_multiline(tmp_path):
    import ast

    import strawberry
    from strawberry.codegen import QueryCodegen
    from strawberry.codegen.plugins.python import PythonPlugin

    @strawberry.type(description='Multi-line\ndescription with "quotes".')
    class Item:
        code: str = strawberry.field(description='Code ending with "quote"')
        notes: str = strawberry.field(description='Notes with """triple quotes"""')

    @strawberry.type
    class Query:
        @strawberry.field(description="Fetches an item.")
        def item(self) -> Item:
            return Item(code="A", notes="B")

    schema = strawberry.Schema(query=Query)
    query_str = """
    query GetItem {
      aliased_item: item {
        aliased_code: code
        notes
      }
    }
    """
    query_file = tmp_path / "item.graphql"
    generator = QueryCodegen(schema, plugins=[PythonPlugin(query_file)])
    result = generator.run(query_str)
    code = result.to_string()

    assert '"""Multi-line\n    description with "quotes"."""' in code
    assert '"""Code ending with "quote" """' in code
    assert r'"""Notes with \"\"\"triple quotes\"\"\" """' in code
    assert '"""Fetches an item."""' in code

    ast.parse(code)
