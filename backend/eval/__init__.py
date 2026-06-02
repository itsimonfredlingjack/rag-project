"""
Svensk Ragg — Evaluation Framework
=========================================

Golden dataset evaluation for Swedish legal RAG quality measurement.

Usage:
    from eval.golden_dataset import GoldenDataset, load_golden_dataset

    dataset = load_golden_dataset()
    for item in dataset:
        print(f"Q: {item.question} | Mode: {item.mode} | Intent: {item.intent}")
"""
