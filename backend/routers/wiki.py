"""Wiki/Knowledge Book router."""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.dependencies.auth import get_current_admin_user
from backend.models.user import User
from backend.models.wiki import WikiPage, KnowledgeInsight
from backend.llm_providers import LLMProvider

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Add console handler for debugging
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s")
console_handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(console_handler)
from backend.models.settings import SystemSettings
from backend.services.rag_anything_service import rag_anything_service


router = APIRouter(prefix="/api/wiki", tags=["wiki"])


def _wiki_source_name(title: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title.strip().lower()).strip("-")
    return f"{slug or 'wiki-page'}.md"


async def _sync_wiki_markdown(title: str, content: str) -> None:
    if not rag_anything_service.is_initialized:
        return
    try:
        await rag_anything_service.ingest_markdown(
            title=title,
            content=f"# {title}\n\n{content}",
            source_name=_wiki_source_name(title),
        )
        logger.info("Updated RAG service index for wiki page: %s", title)
    except Exception as exc:
        logger.error("Failed to update RAG service for wiki page %s: %s", title, exc)


class WikiPageResponse(BaseModel):
    id: int
    title: str
    content: Optional[str]
    source_type: str
    parent_id: Optional[int] = None
    is_folder: bool = False
    created_at: str
    updated_at: str
    version: int = 1

    class Config:
        from_attributes = True


class WikiPageCreate(BaseModel):
    title: Optional[str] = None
    content: str = ""
    source_type: str = "note"
    parent_id: Optional[int] = None
    is_folder: bool = False


@router.get("")
async def get_wiki_pages(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Get all wiki pages (admin only)."""
    result = await db.execute(
        select(WikiPage)
        .options(selectinload(WikiPage.versions))
        .order_by(desc(WikiPage.updated_at))
        .offset(skip)
        .limit(limit)
    )
    pages = result.scalars().all()

    inputs = []
    outputs = []

    for p in pages:
        page_resp = WikiPageResponse(
            id=p.id,
            title=p.title,
            content=p.content,
            source_type=p.source_type,
            parent_id=p.parent_id,
            is_folder=p.is_folder,
            created_at=p.created_at.isoformat(),
            updated_at=p.updated_at.isoformat(),
            version=len(p.versions) + 1 if p.versions else 1,
        )
        if p.is_processed:
            outputs.append(page_resp)
        else:
            inputs.append(page_resp)

    return {"inputs": inputs, "outputs": outputs}


@router.get("/search")
async def search_wiki(
    q: str,
    limit: int = 5,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Search wiki content for relevant pages."""
    # Get all processed wiki pages
    result = await db.execute(
        select(WikiPage)
        .where(WikiPage.is_processed == True)
        .where(WikiPage.is_folder == False)  # Only actual pages, not folders
        .where(WikiPage.content.isnot(None))
    )
    pages = result.scalars().all()

    if not pages:
        return {"results": []}

    # Simple text search - find pages with matching content
    results = []
    q_lower = q.lower()
    for page in pages:
        if page.content and (
            q_lower in page.content.lower() or q_lower in page.title.lower()
        ):
            # Extract relevant snippet
            content_lower = page.content.lower()
            pos = content_lower.find(q_lower)
            if pos >= 0:
                start = max(0, pos - 50)
                end = min(len(page.content), pos + 150)
                snippet = (
                    ("..." if start > 0 else "")
                    + page.content[start:end]
                    + ("..." if end < len(page.content) else "")
                )
            else:
                snippet = (
                    page.content[:200] + "..."
                    if len(page.content) > 200
                    else page.content
                )

            results.append(
                {
                    "id": page.id,
                    "title": page.title,
                    "content": snippet,
                    "score": 1.0,  # Simple scoring
                }
            )

    # Sort by relevance (content match first, then title match)
    results.sort(
        key=lambda x: (
            x["content"].lower().count(q_lower),
            x["title"].lower().count(q_lower),
        ),
        reverse=True,
    )

    return {"results": results[:limit]}


@router.get("/{page_id}", response_model=WikiPageResponse)
async def get_wiki_page(
    page_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Get a specific wiki page (admin only)."""
    result = await db.execute(
        select(WikiPage)
        .options(selectinload(WikiPage.versions))
        .where(WikiPage.id == page_id)
    )
    page = result.scalar_one_or_none()

    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Wiki page not found"
        )

    return WikiPageResponse(
        id=page.id,
        title=page.title,
        content=page.content,
        source_type=page.source_type,
        created_at=page.created_at.isoformat(),
        updated_at=page.updated_at.isoformat(),
        version=len(page.versions) + 1 if page.versions else 1,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=WikiPageResponse)
async def create_wiki_page(
    page_data: WikiPageCreate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Create a new quick note (input) and auto-merge into wiki."""
    logger.info(f"Creating note, content length: {len(page_data.content or '')}")
    content = page_data.content or ""

    db_page = WikiPage(
        title="Note",
        content=content if content else None,
        source_type=page_data.source_type,
        source_id=None,
        parent_id=page_data.parent_id,
        is_folder=page_data.is_folder,
        is_draft=False,
        is_processed=page_data.is_folder,  # Folders are processed, notes are inputs
        created_by_id=current_user.id,
    )
    db.add(db_page)
    await db.commit()
    await db.refresh(db_page)

    # Only auto-merge for notes, not folders
    if not page_data.is_folder:
        logger.info("Calling auto_merge_note_to_wiki...")
        try:
            await auto_merge_note_to_wiki(
                db, "Note", content, current_user.id, db_page.id
            )
            logger.info("Auto-merge completed successfully")
        except Exception as e:
            logger.error(f"Auto-merge failed with error: {e}", exc_info=True)
            # Continue anyway, don't fail the note creation

    return WikiPageResponse(
        id=db_page.id,
        title=db_page.title,
        content=db_page.content,
        source_type=db_page.source_type,
        parent_id=db_page.parent_id,
        is_folder=db_page.is_folder,
        created_at=db_page.created_at.isoformat(),
        updated_at=db_page.updated_at.isoformat(),
        version=1,
    )


async def auto_merge_note_to_wiki(
    db: AsyncSession, title: str, content: str, user_id: int, note_id: int = None
):
    """Automatically merge a new note into existing wiki or create new."""
    logger.info(f"Starting auto-merge for note: {title[:30]}...")

    try:
        # Get system settings
        result = await db.execute(select(SystemSettings).limit(1))
        settings = result.scalar_one_or_none()

        logger.info(
            f"LLM settings: provider={settings.llm_provider if settings else 'None'}, model={settings.llm_model if settings else 'None'}, has_key=/{settings.llm_api_key[:10] if settings and settings.llm_api_key else 'None'}"
        )

        if not settings or not settings.llm_api_key:
            logger.info("No LLM configured, skipping auto-merge")
            return

        logger.info("LLM configured, proceeding with auto-merge")
        logger.info(
            f"LLM Provider: {settings.llm_provider}, Model: {settings.llm_model}"
        )

        # Get all existing wiki pages (outputs)
        result_wiki = await db.execute(
            select(WikiPage)
            .where(WikiPage.is_processed == True)
            .order_by(desc(WikiPage.updated_at))
        )
        all_wiki = result_wiki.scalars().all()

        llm_provider = LLMProvider(
            settings.llm_provider or "openai",
            settings.llm_model or "gpt-4o-mini",
            settings.llm_api_key,
        )
        llm = llm_provider.get_llm()
        logger.info(f"LLM obtained: {llm}")

        if not llm:
            logger.error("Failed to get LLM instance, returning")
            return

        logger.info("LLM ready, checking for existing wiki pages...")
        logger.info(f"all_wiki count: {len(all_wiki) if all_wiki else 0}")
        logger.info(f"all_wiki is: {all_wiki!r}, bool: {bool(all_wiki)}")
        from langchain_core.messages import HumanMessage

        if all_wiki:
            # Ask LLM to decide which wiki to use or if new should be created
            wiki_list = "\n".join([f"- {wiki.id}: {wiki.title}" for wiki in all_wiki])

            decide_prompt = f"""Given the new note below, decide what to do with it.

Existing Wikis:
{wiki_list}

New Note:
---
Title: {title}
Content: {content[:500]}
---

Respond in this exact format:
- If should merge into existing wiki: "MERGE: <wiki_id>"
- If should create new wiki: "NEW"

Only respond with one line, nothing else."""

            decide_response = await llm.ainvoke([HumanMessage(content=decide_prompt)])
            decision = decide_response.content.strip()
            logger.info(f"LLM decision: {decision}")

            if decision.startswith("MERGE:"):
                try:
                    wiki_id = int(decision.split(":")[1].strip())
                    best_wiki = next((w for w in all_wiki if w.id == wiki_id), None)
                except Exception as e:
                    logger.warning(f"Failed to parse wiki_id: {e}")
                    best_wiki = None

                if best_wiki:
                    merge_prompt = f"""You have existing wiki content and a new note. 

Existing Wiki:
---
{best_wiki.content}
---

New Note:
---
Title: {title}
Content: {content}
---

Integrate the new note into the existing wiki naturally. Update, expand, or add to the wiki as appropriate. 
Return the updated wiki content in markdown format."""

                    response = await llm.ainvoke([HumanMessage(content=merge_prompt)])

                    best_wiki.content = response.content
                    best_wiki.updated_at = datetime.utcnow()
                    await db.commit()
                    logger.info(f"Merged note into wiki: {best_wiki.id}")

                    await _sync_wiki_markdown(best_wiki.title, best_wiki.content)

                    return  # Done, don't create new
            else:
                # No existing wikis, create new wiki directly
                logger.info("ENTERED ELSE BLOCK - no existing wikis, creating new")
                logger.info(
                    f"Creating new wiki (no existing wikis). Note title: '{title}', content preview: {content[:100]}..."
                )
                create_prompt = f"""Create a well-structured wiki page from this note.

Note:
---
Title: {title}
Content: {content}
---

Return a JSON object with:
- "title": A short, descriptive title for this wiki (max 50 chars)
- "content": The wiki content in markdown format

Example: {{"title": "Important Dates", "content": "# Important Dates\\n\\n..."}}"""

                response = await llm.ainvoke([HumanMessage(content=create_prompt)])

                import json
                import re

                match = re.search(r"\{.*\}", response.content, re.DOTALL)
                if match:
                    wiki_data = json.loads(match.group())
                    wiki_title = wiki_data.get("title", "Untitled")
                    wiki_content = wiki_data.get("content", response.content)
                else:
                    wiki_title = "Untitled"
                    wiki_content = response.content

                db_wiki = WikiPage(
                    title=wiki_title,
                    content=wiki_content,
                    source_type="merged",
                    source_id=note_id,
                    is_draft=False,
                    is_processed=True,
                    created_by_id=user_id,
                )
                db.add(db_wiki)
                await db.commit()
                logger.info(f"Created new wiki from note")

                await _sync_wiki_markdown(wiki_title, wiki_content)
                return

        # No existing wikis, create new wiki directly
        logger.info("ENTERED ELSE BLOCK - no existing wikis, creating new")
        logger.info(
            f"Creating new wiki (no existing wikis). Note title: '{title}', content preview: {content[:100]}..."
        )
        create_prompt = f"""Create a well-structured wiki page from this note.

Note:
---
Title: {title}
Content: {content}
---

Return a JSON object with:
- "title": A short, descriptive title for this wiki (max 50 chars)
- "content": The wiki content in markdown format

Example: {{"title": "Important Dates", "content": "# Important Dates\\n\\n..."}}"""

        response = await llm.ainvoke([HumanMessage(content=create_prompt)])

        import json
        import re

        match = re.search(r"\{.*\}", response.content, re.DOTALL)
        if match:
            wiki_data = json.loads(match.group())
            wiki_title = wiki_data.get("title", "Untitled")
            wiki_content = wiki_data.get("content", response.content)
        else:
            wiki_title = "Untitled"
            wiki_content = response.content

        db_wiki = WikiPage(
            title=wiki_title,
            content=wiki_content,
            source_type="merged",
            source_id=note_id,
            is_draft=False,
            is_processed=True,
            created_by_id=user_id,
        )
        db.add(db_wiki)
        await db.commit()
        logger.info(f"Created new wiki from note")

        await _sync_wiki_markdown(wiki_title, wiki_content)

    except Exception as e:
        logger.error(f"Auto-merge failed: {e}")


class MergeRequest(BaseModel):
    page_ids: List[int]
    merged_title: str


@router.post(
    "/merge", status_code=status.HTTP_201_CREATED, response_model=WikiPageResponse
)
async def merge_to_wiki(
    request: MergeRequest,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Merge multiple input pages into a single wiki page (output)."""
    page_ids = request.page_ids
    merged_title = request.merged_title

    # Get all input pages
    result = await db.execute(select(WikiPage).where(WikiPage.id.in_(page_ids)))
    pages = result.scalars().all()

    if not pages:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No pages found to merge"
        )

    # Get system settings for LLM
    result_settings = await db.execute(select(SystemSettings).limit(1))
    settings = result_settings.scalar_one_or_none()

    # Combine content intelligently using LLM if available
    if settings and settings.llm_api_key:
        try:
            from langchain_core.messages import HumanMessage

            llm_provider = LLMProvider(
                settings.llm_provider or "openai",
                settings.llm_model or "gpt-4o-mini",
                settings.llm_api_key,
            )
            llm = llm_provider.get_llm()

            if llm:
                # Build content to merge
                content_list = "\n\n".join(
                    [
                        f"--- Source {i + 1} ---\n{p.title}: {p.content}"
                        for i, p in enumerate(pages)
                    ]
                )

                merge_prompt = f"""Merge the following related notes into a single coherent document. 
Remove duplicates, combine similar information, and organize logically.

{content_list}

Return the merged document in markdown format with a clear structure."""

                response = await llm.ainvoke([HumanMessage(content=merge_prompt)])
                combined_content = response.content
            else:
                combined_content = "\n\n---\n\n".join(
                    [f"## {p.title}\n\n{p.content}" for p in pages]
                )
        except Exception as e:
            import logging

            logging.getLogger(__name__).error(f"LLM merge failed: {e}")
            combined_content = "\n\n---\n\n".join(
                [f"## {p.title}\n\n{p.content}" for p in pages]
            )
    else:
        combined_content = "\n\n---\n\n".join(
            [f"## {p.title}\n\n{p.content}" for p in pages]
        )

    # Create merged wiki page
    db_wiki = WikiPage(
        title=merged_title,
        content=combined_content,
        source_type="merged",
        source_id=None,
        is_draft=False,
        is_processed=True,  # Output - processed wiki
        created_by_id=current_user.id,
    )
    db.add(db_wiki)
    await db.commit()
    await db.refresh(db_wiki)

    return WikiPageResponse(
        id=db_wiki.id,
        title=db_wiki.title,
        content=db_wiki.content,
        source_type=db_wiki.source_type,
        created_at=db_wiki.created_at.isoformat(),
        updated_at=db_wiki.updated_at.isoformat(),
        version=1,
    )


@router.post("/{page_id}/process")
async def process_wiki_page(
    page_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Process a wiki page and regenerate insights."""
    result = await db.execute(
        select(WikiPage)
        .options(selectinload(WikiPage.versions))
        .where(WikiPage.id == page_id)
    )
    page = result.scalar_one_or_none()

    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Wiki page not found"
        )

    # Regenerate insights and sync the page to the external RAG service
    await generate_insights_from_note(db, page.title, page.content, current_user.id)

    return {"message": "Page processed successfully"}


@router.delete("/{page_id}")
async def delete_wiki_page(
    page_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Delete a wiki page (admin only)."""
    result = await db.execute(select(WikiPage).where(WikiPage.id == page_id))
    page = result.scalar_one_or_none()

    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Wiki page not found"
        )

    await db.delete(page)
    await db.commit()

    return {"message": "Wiki page deleted successfully"}


async def generate_insights_from_note(
    db: AsyncSession, title: str, content: str, user_id: int
):
    """Generate knowledge insights from note content using LLM."""
    import json
    import re
    import logging

    logger = logging.getLogger(__name__)

    try:
        result = await db.execute(select(SystemSettings).limit(1))
        settings = result.scalar_one_or_none()

        if not settings or not settings.llm_api_key:
            logger.info("No LLM configured, skipping insight generation")
            return

        llm_provider = LLMProvider(
            settings.llm_provider or "openai",
            settings.llm_model or "gpt-4o-mini",
            settings.llm_api_key,
        )
        llm = llm_provider.get_llm()

        if not llm:
            logger.warning("Failed to get LLM, skipping insight generation")
            return

        from langchain_core.messages import HumanMessage

        insight_prompt = f"""Analyze the following note and extract 1-3 key knowledge insights that could be useful for a knowledge base. 

Title: {title}
Content: {content}

Return ONLY a JSON array of insights, like:
[{{"content": "insight text", "tags": ["fact"]}}]"""

        response = await llm.ainvoke([HumanMessage(content=insight_prompt)])

        match = re.search(r"\[.*\]", response.content, re.DOTALL)
        if match:
            insights_data = json.loads(match.group())

            for insight in insights_data:
                db_insight = KnowledgeInsight(
                    title=f"Insight from: {title}",
                    content=insight.get("content", ""),
                    source_type="note_generated",
                    source_user_id=user_id,
                    status="pending",
                    tags=insight.get("tags", []),
                )
                db.add(db_insight)

            await db.commit()
            logger.info(f"Generated {len(insights_data)} insights from note")

    except Exception as e:
        logger.error(f"Failed to generate insights: {e}")

    await _sync_wiki_markdown(title, content)
