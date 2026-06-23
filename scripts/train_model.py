"""Train the flood risk prediction ML model."""

import os
import sys

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from core.db import init_db
from core.ml_model import train_risk_model


def main():
    init_db()
    print("Training risk prediction model...")
    result = train_risk_model()

    print(f"\nAccuracy: {result['accuracy']:.4f}")
    print(f"\nClassification Report:\n{result['classification_report']}")
    print(f"Train samples: {result['n_train_samples']}")
    print(f"Test samples: {result['n_test_samples']}")
    print(f"\nFeature Importance:")
    for feat, imp in result["feature_importance"].items():
        print(f"  {feat}: {imp:.4f}")

    print(
        "\nModel trained on limited real data. This model enhances but does not "
        "replace the rule-based risk engine. Always display both scores in the UI "
        "with their source labeled."
    )


if __name__ == "__main__":
    main()
