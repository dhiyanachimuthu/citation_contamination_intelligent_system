"""
Citation Contamination Intelligence System — CLI pipeline entry point.

Usage:
    python main.py <DOI>
    python main.py 10.1038/nbt.3816
    python main.py --process-data     # re-process retraction_watch.csv
"""

import sys
import os
import json
import logging
import argparse

sys.path.insert(0, os.path.dirname(__file__))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def cmd_process_data():
    from process_data import process
    result = process()
    stats = result.get("stats", {})
    print(f"\n✓ Processed retraction_watch.csv")
    print(f"  DOIs indexed : {stats.get('with_doi', 0):,}")
    print(f"  Title-only   : {stats.get('without_doi', 0):,}")
    print(f"  Total rows   : {stats.get('total_rows', 0):,}")


def cmd_analyze(doi_input: str):
    from modules.pipeline import run_analysis

    print(f"\nAnalyzing: {doi_input}")
    print("─" * 60)

    result = run_analysis(doi_input)

    if not result["success"]:
        print(f"✗ Error: {result['error']}")
        sys.exit(1)

    root_doi    = result["root_doi"]
    retraction  = result["retraction"]
    papers      = result["papers"]
    node_count  = result["node_count"]
    edge_count  = result["edge_count"]

    # Retraction status
    if retraction["is_retracted"]:
        print(f"⚠  RETRACTED")
        print(f"   Reason : {retraction.get('reason') or 'N/A'}")
        print(f"   Year   : {retraction.get('year') or 'N/A'}")
    else:
        print("✓  Not found in Retraction Watch")

    print(f"\nGraph: {node_count} nodes, {edge_count} edges")

    high_risk     = [p for p in papers if p.get("risk_level") == "HIGH"]
    medium_risk   = [p for p in papers if p.get("risk_level") == "MEDIUM"]
    low_risk      = [p for p in papers if p.get("risk_level") == "LOW"]
    retracted_net = [p for p in papers if p.get("is_retracted")]

    print(f"Risk breakdown: HIGH={len(high_risk)}  MEDIUM={len(medium_risk)}  LOW={len(low_risk)}")
    print(f"Retracted in network: {len(retracted_net)}")

    print("\nTop 10 highest-risk papers:")
    print(f"{'#':<4} {'Risk':>7}  {'Lvl':<6}  {'D':>2}  {'DOI'}")
    print("─" * 70)
    for i, p in enumerate(papers[:10], 1):
        title_short = (p.get("title") or "NULL")[:40]
        print(
            f"{i:<4} {p['risk_score']:>7.3f}  {p['risk_level']:<6}  "
            f"{p['depth_level']:>2}  {p['doi'][:40]}"
        )
        if p.get("title"):
            print(f"          {title_short}")

    out_path = os.path.join(
        os.path.dirname(__file__), "data",
        f"results_{root_doi.replace('/', '_')}.json"
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        serializable = {
            k: v for k, v in result.items() if k != "graph"
        }
        json.dump(serializable, f, indent=2, default=str)

    print(f"\n✓ Full results saved to: {out_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Citation Contamination Intelligence System"
    )
    parser.add_argument("doi", nargs="?", help="DOI to analyze")
    parser.add_argument("--process-data", action="store_true", help="Re-process retraction_watch.csv")
    args = parser.parse_args()

    if args.process_data:
        cmd_process_data()
    elif args.doi:
        cmd_analyze(args.doi)
    else:
        parser.print_help()
        print("\nExamples:")
        print("  python main.py 10.1038/nbt.3816")
        print("  python main.py --process-data")


if __name__ == "__main__":
    main()
