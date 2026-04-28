"""
Motor de predicción con auto-aprendizaje.
Guarda cada predicción, verifica resultados, y ajusta pesos automáticamente.
"""
import json
import os
import logging
from datetime import datetime, timedelta
from pathlib import Path
from copy import deepcopy

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
PREDICTIONS_FILE = DATA_DIR / "predictions_history.json"
WEIGHTS_FILE = DATA_DIR / "learned_weights.json"
STATS_FILE = DATA_DIR / "accuracy_stats.json"

# Tasa de aprendizaje — qué tanto ajustar los pesos tras cada verificación
LEARNING_RATE = 0.02


def _ensure_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_json(filepath: Path) -> dict | list:
    """Carga un archivo JSON o retorna estructura vacía."""
    if filepath.exists():
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {} if "weights" in str(filepath) or "stats" in str(filepath) else []


def _save_json(filepath: Path, data):
    """Guarda datos en un archivo JSON."""
    _ensure_dir()
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ================================================================
# PESOS ADAPTATIVOS
# ================================================================

def get_weights(sport: str) -> dict:
    """
    Obtiene los pesos actuales para un deporte.
    Si hay pesos aprendidos, los usa. Si no, usa los iniciales.
    
    Args:
        sport: 'football', 'nba', o 'lol'
    
    Returns:
        Dict con los pesos de cada factor
    """
    from config import (
        INITIAL_WEIGHTS_FOOTBALL,
        INITIAL_WEIGHTS_NBA,
        INITIAL_WEIGHTS_LOL,
    )

    defaults = {
        "football": INITIAL_WEIGHTS_FOOTBALL,
        "nba": INITIAL_WEIGHTS_NBA,
        "lol": INITIAL_WEIGHTS_LOL,
    }

    learned = _load_json(WEIGHTS_FILE)
    if sport in learned:
        return learned[sport]
    
    return deepcopy(defaults.get(sport, {}))


def save_weights(sport: str, weights: dict):
    """Guarda pesos aprendidos para un deporte."""
    learned = _load_json(WEIGHTS_FILE)
    learned[sport] = weights
    _save_json(WEIGHTS_FILE, learned)


def _normalize_weights(weights: dict) -> dict:
    """Normaliza los pesos para que sumen 1.0."""
    total = sum(weights.values())
    if total == 0:
        n = len(weights)
        return {k: 1.0 / n for k in weights}
    return {k: v / total for k, v in weights.items()}


# ================================================================
# PREDICCIÓN
# ================================================================

class Prediction:
    """Representa una predicción individual."""

    def __init__(
        self,
        sport: str,
        league: str,
        home_team: str,
        away_team: str,
        predicted_winner: str,
        confidence: float,
        factors: dict,
        factor_scores: dict,
        event_id: str = None,
    ):
        self.sport = sport
        self.league = league
        self.home_team = home_team
        self.away_team = away_team
        self.predicted_winner = predicted_winner
        self.confidence = round(confidence, 1)
        self.factors = factors          # Descripción legible de cada factor
        self.factor_scores = factor_scores  # Score numérico de cada factor
        self.event_id = event_id
        self.timestamp = datetime.now().isoformat()
        self.verified = False
        self.actual_winner = None
        self.correct = None

    def to_dict(self) -> dict:
        return {
            "sport": self.sport,
            "league": self.league,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "predicted_winner": self.predicted_winner,
            "confidence": self.confidence,
            "factors": self.factors,
            "factor_scores": self.factor_scores,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "verified": self.verified,
            "actual_winner": self.actual_winner,
            "correct": self.correct,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Prediction":
        pred = cls(
            sport=data["sport"],
            league=data["league"],
            home_team=data["home_team"],
            away_team=data["away_team"],
            predicted_winner=data["predicted_winner"],
            confidence=data["confidence"],
            factors=data.get("factors", {}),
            factor_scores=data.get("factor_scores", {}),
            event_id=data.get("event_id"),
        )
        pred.timestamp = data.get("timestamp", "")
        pred.verified = data.get("verified", False)
        pred.actual_winner = data.get("actual_winner")
        pred.correct = data.get("correct")
        return pred


def calculate_prediction(
    sport: str,
    league: str,
    home_team: str,
    away_team: str,
    factor_scores: dict,
    factors_description: dict,
    event_id: str = None,
) -> Prediction:
    """
    Calcula una predicción usando los pesos adaptativos.
    
    Args:
        sport: 'football', 'nba', 'lol'
        league: Nombre de la liga
        home_team: Equipo local / equipo 1
        away_team: Equipo visitante / equipo 2
        factor_scores: Dict {factor_name: score} donde score > 0.5 favorece home,
                       score < 0.5 favorece away, 0.5 = neutral
        factors_description: Dict {factor_name: "descripción legible"}
        event_id: ID del evento en la API (para verificación)
    
    Returns:
        Prediction object
    """
    weights = get_weights(sport)

    # Calcular score ponderado para el equipo local
    home_score = 0.0
    total_weight = 0.0

    for factor, weight in weights.items():
        if factor in factor_scores:
            home_score += factor_scores[factor] * weight
            total_weight += weight

    if total_weight > 0:
        home_score /= total_weight
    else:
        home_score = 0.5

    # Determinar ganador y confianza
    if home_score >= 0.5:
        predicted_winner = home_team
        confidence = 50 + (home_score - 0.5) * 100  # 50-100%
    else:
        predicted_winner = away_team
        confidence = 50 + (0.5 - home_score) * 100  # 50-100%

    # Limitar confianza a rango razonable (52-88%)
    confidence = max(52.0, min(88.0, confidence))

    prediction = Prediction(
        sport=sport,
        league=league,
        home_team=home_team,
        away_team=away_team,
        predicted_winner=predicted_winner,
        confidence=confidence,
        factors=factors_description,
        factor_scores=factor_scores,
        event_id=event_id,
    )

    # Guardar predicción en historial
    save_prediction(prediction)

    return prediction


# ================================================================
# HISTORIAL Y TRACKING
# ================================================================

def save_prediction(prediction: Prediction):
    """Guarda una predicción en el historial."""
    history = _load_json(PREDICTIONS_FILE)
    
    # Evitar duplicados por event_id
    if prediction.event_id:
        history = [
            p for p in history 
            if p.get("event_id") != prediction.event_id
        ]
    
    history.append(prediction.to_dict())
    
    # Mantener solo los últimos 500 registros
    if len(history) > 500:
        history = history[-500:]
    
    _save_json(PREDICTIONS_FILE, history)


def verify_prediction(event_id: str, actual_winner: str) -> bool | None:
    """
    Verifica una predicción con el resultado real y ajusta pesos.
    
    Args:
        event_id: ID del evento
        actual_winner: Nombre del equipo ganador real
    
    Returns:
        True si acertó, False si falló, None si no encontró la predicción
    """
    history = _load_json(PREDICTIONS_FILE)
    
    prediction_data = None
    for p in history:
        if p.get("event_id") == event_id and not p.get("verified"):
            prediction_data = p
            break
    
    if prediction_data is None:
        return None

    prediction_data["verified"] = True
    prediction_data["actual_winner"] = actual_winner
    
    # Determinar si acertó
    predicted = prediction_data["predicted_winner"].lower()
    actual = actual_winner.lower()
    correct = predicted in actual or actual in predicted
    prediction_data["correct"] = correct

    _save_json(PREDICTIONS_FILE, history)

    # Ajustar pesos basado en resultado
    _adjust_weights(prediction_data)

    # Actualizar estadísticas
    _update_stats(prediction_data["sport"], correct)

    return correct


def _adjust_weights(prediction_data: dict):
    """
    Auto-aprendizaje: ajusta los pesos basado en qué factores
    contribuyeron a una predicción correcta/incorrecta.
    
    Si la predicción fue correcta:
        - Los factores que "votaron" por el ganador se refuerzan
    Si fue incorrecta:
        - Los factores que "votaron" por el ganador incorrecto se debilitan
    """
    sport = prediction_data["sport"]
    weights = get_weights(sport)
    factor_scores = prediction_data.get("factor_scores", {})
    correct = prediction_data.get("correct", False)
    predicted = prediction_data["predicted_winner"]
    home = prediction_data["home_team"]

    predicted_is_home = predicted.lower() in home.lower() or home.lower() in predicted.lower()

    for factor, weight in weights.items():
        if factor not in factor_scores:
            continue

        score = factor_scores[factor]
        
        # ¿Este factor "votó" correctamente?
        factor_favors_home = score > 0.5
        
        if predicted_is_home:
            factor_agreed = factor_favors_home
        else:
            factor_agreed = not factor_favors_home

        if correct:
            if factor_agreed:
                # Factor acertó junto con la predicción → reforzar
                weights[factor] += LEARNING_RATE
            # Si no estuvo de acuerdo pero la predicción acertó, no cambiar mucho
        else:
            if factor_agreed:
                # Factor votó con la predicción incorrecta → debilitar
                weights[factor] -= LEARNING_RATE
            else:
                # Factor votó contra la predicción incorrecta → reforzar
                weights[factor] += LEARNING_RATE * 0.5

        # Mantener pesos en rango razonable
        weights[factor] = max(0.05, min(0.50, weights[factor]))

    # Normalizar pesos
    weights = _normalize_weights(weights)
    save_weights(sport, weights)
    
    logger.info(f"Pesos actualizados para {sport}: {weights}")


# ================================================================
# ESTADÍSTICAS DE ACIERTO
# ================================================================

def _update_stats(sport: str, correct: bool):
    """Actualiza las estadísticas de acierto."""
    stats = _load_json(STATS_FILE)
    
    month_key = datetime.now().strftime("%Y-%m")
    
    if sport not in stats:
        stats[sport] = {}
    if month_key not in stats[sport]:
        stats[sport][month_key] = {"correct": 0, "total": 0}
    if "all_time" not in stats[sport]:
        stats[sport]["all_time"] = {"correct": 0, "total": 0}

    stats[sport][month_key]["total"] += 1
    stats[sport]["all_time"]["total"] += 1
    
    if correct:
        stats[sport][month_key]["correct"] += 1
        stats[sport]["all_time"]["correct"] += 1

    _save_json(STATS_FILE, stats)


def get_accuracy_stats() -> dict:
    """
    Obtiene estadísticas de acierto del bot.
    
    Returns:
        Dict con stats por deporte y mes
    """
    stats = _load_json(STATS_FILE)
    
    result = {}
    month_key = datetime.now().strftime("%Y-%m")
    
    for sport in ["football", "nba", "lol"]:
        sport_stats = stats.get(sport, {})
        monthly = sport_stats.get(month_key, {"correct": 0, "total": 0})
        all_time = sport_stats.get("all_time", {"correct": 0, "total": 0})
        
        result[sport] = {
            "monthly": {
                "correct": monthly["correct"],
                "total": monthly["total"],
                "accuracy": (
                    round(monthly["correct"] / monthly["total"] * 100, 1)
                    if monthly["total"] > 0 else 0
                ),
            },
            "all_time": {
                "correct": all_time["correct"],
                "total": all_time["total"],
                "accuracy": (
                    round(all_time["correct"] / all_time["total"] * 100, 1)
                    if all_time["total"] > 0 else 0
                ),
            },
        }

    return result


def get_unverified_predictions() -> list:
    """Obtiene predicciones que aún no han sido verificadas."""
    history = _load_json(PREDICTIONS_FILE)
    return [p for p in history if not p.get("verified", False)]


def get_current_weights() -> dict:
    """Obtiene todos los pesos actuales para mostrar al usuario."""
    return {
        "football": get_weights("football"),
        "nba": get_weights("nba"),
        "lol": get_weights("lol"),
    }
