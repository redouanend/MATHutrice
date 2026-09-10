import sys
import os

# Ajout du chemin pour pouvoir importer le module créé
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from latex_validator import validate_latex_syntax

def run_tests():
    test_cases = [
        {
            "name": "✅ Cas de succès (Syntaxe correcte)",
            "input": "Calcule \\(x^2 + 1\\) puis \\[\\frac{a}{b}\\]",
            "expected_success": True
        },
        {
            "name": "❌ Échec (Délimiteurs obsolètes $ détectés)",
            "input": "Calcule $x^2 + 1$ puis $\\frac{a}{b}$",
            "expected_success": False
        },
        {
            "imbalance_type": "inline",
            "name": "❌ Échec (Délimiteur inline non fermé \\()",
            "input": "Calcule \\(x^2 + 1$ sans fermer",
            "expected_success": False
        },
        {
            "imbalance_type": "block",
            "name": "❌ Échec (Délimiteur de bloc non fermé \\[)",
            "input": "Calcul de bloc \\[\\frac{1}{2} sans fin",
            "expected_success": False
        }
    ]

    print("\n" + "═" * 60)
    print("  VÉRIFICATION RÉELLE — ISSUE #8 (LaTeX Validator)")
    print("═" * 60)

    passed = 0
    total = len(test_cases)

    for case in test_cases:
        is_valid, reason = validate_latex_syntax(case["input"])

        status = "PASS" if is_valid == case["expected_success"] else "FAIL"

        if status == "PASS":
            passed += 1
            symbol = "✅"
        else:
            symbol = "❌"

        print(f"{symbol} {case['name']}")
        if not is_valid:
            print(f"    > Erreur détectée : {reason}")
        print(f"    > Résultat : {'Valide' if is_valid else 'Invalide'}")
        print("-" * 40)

    print(f"\nSCORE FINAL : {passed}/{total} tests réussis.")
    print("═" * 60 + "\n")

    if passed == total:
        print("🚀 ISSUE #8 VALIDÉE AVEC SUCCÈS !")
        return True
    else:
        print("⚠️ ÉCHEC DE LA VALIDATION.")
        return False

if __name__ == "__main__":
    success = run_tests()
    if not success:
        exit(1)
