"""MCP Prompts for common knowledge base tasks."""

from mcp.server import Server
from mcp.types import GetPromptResult, Prompt, PromptArgument, PromptMessage, TextContent

from .config import Config


def register_prompts(server: Server, config: Config) -> None:
    """Register MCP prompts."""

    @server.list_prompts()
    async def list_prompts() -> list[Prompt]:
        return [
            Prompt(
                name="answer_question",
                description="Answer a question using the knowledge base",
                arguments=[
                    PromptArgument(
                        name="question",
                        description="The question to answer",
                        required=True,
                    ),
                    PromptArgument(
                        name="collection",
                        description="Limit search to specific collection (optional)",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="summarize_document",
                description="Summarize a document from the knowledge base",
                arguments=[
                    PromptArgument(
                        name="document_path",
                        description="Path to the document",
                        required=True,
                    ),
                ],
            ),
            Prompt(
                name="compare_documents",
                description="Compare two documents on a specific topic",
                arguments=[
                    PromptArgument(
                        name="doc1",
                        description="Path to first document",
                        required=True,
                    ),
                    PromptArgument(
                        name="doc2",
                        description="Path to second document",
                        required=True,
                    ),
                    PromptArgument(
                        name="topic",
                        description="Topic to compare",
                        required=True,
                    ),
                ],
            ),
        ]

    @server.get_prompt()
    async def get_prompt(name: str, arguments: dict | None) -> GetPromptResult:
        args = arguments or {}

        if name == "answer_question":
            messages = _answer_question_prompt(args)
        elif name == "summarize_document":
            messages = _summarize_document_prompt(args)
        elif name == "compare_documents":
            messages = _compare_documents_prompt(args)
        else:
            raise ValueError(f"Unknown prompt: {name}")

        return GetPromptResult(messages=messages)


def _answer_question_prompt(args: dict) -> list[PromptMessage]:
    """Generate answer_question prompt."""
    question = args.get("question", "")
    collection = args.get("collection", "")

    scope_instruction = ""
    if collection:
        scope_instruction = f"\n\nLimit your search to the '{collection}' collection."

    return [
        PromptMessage(
            role="user",
            content=TextContent(
                type="text",
                text=f"""Answer this question using the knowledge base: {question}
{scope_instruction}
Instructions:
1. First use list_collections to understand what documents are available
2. Use find_document if you need to locate a specific document
3. Use search_documents to find relevant content
4. Quote directly from the sources when possible
5. Include page numbers or section names in citations
6. If the answer is not found, say so clearly

Format your answer with:
- Direct quotes from sources (in quotation marks)
- Source citations (document name, page/section)
- Brief explanation if the quote needs clarification""",
            ),
        )
    ]


def _summarize_document_prompt(args: dict) -> list[PromptMessage]:
    """Generate summarize_document prompt."""
    document_path = args.get("document_path", "")

    return [
        PromptMessage(
            role="user",
            content=TextContent(
                type="text",
                text=f"""Summarize the document at: {document_path}

Instructions:
1. Use get_document_info to see the document structure and TOC
2. Use read_document to get the content (you may need to read in chunks)
3. Provide a structured summary including:
   - Main topic/purpose of the document
   - Key sections and their main points
   - Important concepts or definitions
   - Any notable tables, figures, or examples

Format: Use markdown with headers for each major section.""",
            ),
        )
    ]


def _compare_documents_prompt(args: dict) -> list[PromptMessage]:
    """Generate compare_documents prompt."""
    doc1 = args.get("doc1", "")
    doc2 = args.get("doc2", "")
    topic = args.get("topic", "")

    return [
        PromptMessage(
            role="user",
            content=TextContent(
                type="text",
                text=f"""Compare these two documents on the topic of "{topic}":
- Document 1: {doc1}
- Document 2: {doc2}

Instructions:
1. Use search_documents to find content about "{topic}" in both documents
2. Use search_multiple if you need to search for related concepts
3. Compare how each document addresses the topic
4. Note similarities and differences
5. Quote specific passages to support your comparison

Format your response as:
## Summary
Brief overview of how each document covers the topic

## Similarities
- Point 1 (with quotes)
- Point 2 (with quotes)

## Differences
- Point 1 (with quotes from each)
- Point 2 (with quotes from each)

## Conclusion
Which document is more comprehensive/clear/etc.""",
            ),
        )
    ]
