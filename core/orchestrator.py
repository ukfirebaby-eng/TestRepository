import fitz  # PyMuPDF
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any

# Import our previously written modules
from core.vault import HybridVault
from core.agents import DeconstructorAgent, ContradictionHunterAgent, FragilityAgent

HUB_MIN_DEPENDENTS = 3


class DiamondOrchestrator:
    def __init__(self, tenant_id: str, document_id: str, document_name: str = "Untitled"):
        self.tenant_id = tenant_id
        self.document_id = document_id
        self.document_name = document_name
        self.vault = HybridVault(tenant_id=tenant_id)

    def _parse_pdf_with_geometry(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Act I: Reads the PDF and extracts block-level text alongside (x0, y0, x1, y1) coordinates.
        """
        doc = fitz.open(file_path)
        chunks = []

        for page_num, page in enumerate(doc):
            blocks = page.get_text("dict").get("blocks", [])
            for block in blocks:
                if block.get("type") == 0:  # Type 0 is text
                    chunk_text = " ".join([span.get("text", "")
                                           for line in block.get("lines", [])
                                           for span in line.get("spans", [])]).strip()

                    if len(chunk_text) > 20:  # Filter out tiny artifacts
                        chunks.append({
                            "chunk_id": str(uuid.uuid4()),
                            "text": chunk_text,
                            "page": page_num + 1,
                            "bbox": block.get("bbox")  # (x0, y0, x1, y1)
                        })
        return chunks

    def _process_single_chunk(self, chunk: Dict[str, Any]) -> None:
        """
        Act II: The worker function for a single thread.
        Saves semantic text to ChromaDB, then builds graph topology in SQLite.
        """
        # 1. Store the raw text and geometry in the Vector DB
        self.vault.insert_document_chunk(
            chunk_id=chunk["chunk_id"],
            document_id=self.document_id,
            text=chunk["text"],
            page=chunk["page"],
            bbox=chunk["bbox"]
        )

        # 2. Force the LLM to deterministically map the text to JSON topology
        topology = DeconstructorAgent.extract_topology(chunk["text"])

        # 3. Save the Nodes and Edges to the Graph DB, permanently linking the source_chunk_id
        if topology.get("nodes") and topology.get("edges"):
            self.vault.insert_graph_topology(
                nodes=topology["nodes"],
                edges=topology["edges"],
                source_chunk_id=chunk["chunk_id"],
                document_id=self.document_id
            )

    def run_ingestion_pipeline(self, file_path: str, max_workers: int = 10) -> None:
        """
        The Main Execution Loop. Orchestrates parallel processing and enforces the synchronization barrier.
        """
        self.vault.insert_document(self.document_id, self.document_name)
        print(f"[*] Orchestrator: Parsing document {self.document_id}...")
        chunks = self._parse_pdf_with_geometry(file_path)
        print(f"[*] Orchestrator: Extracted {len(chunks)} geometric chunks. Beginning parallel Deconstruction.")

        # Spin up concurrent threads to blast through the document chunk-by-chunk
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(self._process_single_chunk, chunk) for chunk in chunks]

            # The Synchronization Barrier: Wait for all threads to finish
            for count, future in enumerate(as_completed(futures), 1):
                try:
                    future.result()  # This will raise any exceptions caught in the thread
                    if count % 10 == 0:
                        print(f"    -> Processed {count}/{len(chunks)} chunks...")
                except Exception as e:
                    print(f"[!] Orchestrator Thread Failed: {e}")

        print("[*] Orchestrator: Ingestion complete. Knowledge Graph is locked and loaded.")

    def interrogate_friction(self) -> List[Dict[str, Any]]:
        """
        Act III: The Hunt. Queries SQLite for paradoxes and asks the AI to synthesize mitigations.
        """
        # Zero-cost structural query
        conflicts = self.vault.get_triangular_conflicts(document_id=self.document_id)
        print(f"[*] Contradiction Hunter: Found {len(conflicts)} structural conflict(s). Synthesizing mitigations...")

        CONFIDENCE_THRESHOLD = 0.65  # Discard weak or spurious conflicts

        verified_diamonds = []
        spurious_count = 0
        for i, conflict in enumerate(conflicts, 1):
            print(f"    -> Verifying conflict {i}/{len(conflicts)}...")
            # Cross over to ChromaDB to get the raw text that caused the clash
            prov_requires = self.vault.get_chunk_provenance(conflict["chunk_requires"])
            prov_blocks = self.vault.get_chunk_provenance(conflict["chunk_blocks"])

            combined_text = f"Claim 1: {prov_requires.get('text')}\nClaim 2: {prov_blocks.get('text')}"

            # Resolve opaque IDs to human-readable names before sending to the LLM
            names = self.vault.get_node_names([conflict['node_a'], conflict['node_b'], conflict['node_c']])
            name_a = names.get(conflict['node_a'], conflict['node_a'])
            name_b = names.get(conflict['node_b'], conflict['node_b'])
            name_c = names.get(conflict['node_c'], conflict['node_c'])
            structural_clash = f'"{name_a}" REQUIRES "{name_b}", but "{name_c}" BLOCKS "{name_b}"'

            # Agent verifies genuineness before committing to analysis
            result = ContradictionHunterAgent.synthesize_mitigation(structural_clash, combined_text)

            if not result.get("is_genuine") or result.get("confidence", 0) < CONFIDENCE_THRESHOLD:
                spurious_count += 1
                print(f"       [skipped — spurious] confidence={result.get('confidence', 0):.2f}")
                continue

            verified_diamonds.append({
                "source": conflict["node_a"],
                "target": conflict["node_c"],
                "diamond": result["analysis"],
                "provenance_ids": [conflict["chunk_requires"], conflict["chunk_blocks"]]
            })

        print(f"[*] Contradiction Hunter: {len(verified_diamonds)} genuine conflict(s) confirmed, {spurious_count} spurious patterns discarded.")
        self.vault.upsert_friction_lines(self.document_id, verified_diamonds)
        return verified_diamonds

    def interrogate_fragility(self) -> None:
        """
        DLI Pass: Identifies hub nodes and verifies their cascade fragility.
        """
        print("[*] DLI: Mapping fragility...")

        CONFIDENCE_THRESHOLD = 0.65

        hub_nodes = self.vault.get_hub_nodes(self.document_id, min_dependents=HUB_MIN_DEPENDENTS)
        print(f"[*] DLI: Found {len(hub_nodes)} hub node candidate(s). Verifying...")

        verified = []
        spurious_count = 0

        for i, hub in enumerate(hub_nodes, 1):
            print(f"    -> Verifying hub {i}/{len(hub_nodes)}: {hub['name']}...")

            # Resolve dependent node IDs to human-readable names.
            # get_node_names returns only rows that exist in the nodes table;
            # any stale edge references are silently omitted — this is intentional.
            dependent_names = list(
                self.vault.get_node_names(hub["dependent_node_ids"]).values()
            )

            # Get source text for this hub node via the edges table
            source_chunk_id = self.vault.get_node_source_chunk(hub["id"], self.document_id)
            if source_chunk_id is None:
                print(f"       [skipped — no source chunk found for hub node {hub['id']}]")
                continue

            chunk_provenance = self.vault.get_chunk_provenance(source_chunk_id)
            source_text = chunk_provenance.get("text", "")

            result = FragilityAgent.analyse(hub["name"], dependent_names, source_text)

            if not result.get("is_genuine") or result.get("confidence", 0) < CONFIDENCE_THRESHOLD:
                spurious_count += 1
                print(f"       [skipped — spurious] confidence={result.get('confidence', 0):.2f}")
                continue

            verified.append({
                "hub_node_id": hub["id"],
                "dependency_count": hub["dependency_count"],
                "insight": result["insight"],
                "cascade_nodes": result["cascade_nodes"]
            })

        self.vault.upsert_fragility_lines(self.document_id, verified)
        print(f"[*] DLI: {len(verified)} fragility point(s) confirmed, {spurious_count} spurious patterns discarded.")
