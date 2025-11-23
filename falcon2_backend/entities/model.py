from pydantic.dataclasses import dataclass
from pydantic import Field
from datetime import timedelta, datetime, timezone
from typing import ClassVar, Optional

from model_runner_client.model_runners.model_runner import ModelRunner

from falcon2_backend.entities.prediction import PredictionParams


@dataclass
class Player:
    crunch_identifier: str  # unique identifier
    name: str


@dataclass
class ModelScore:
    recent: Optional[float] = None
    steady: Optional[float] = None
    anchor: Optional[float] = None

    # --- WINDOW CONSTANTS ---
    WINDOW_RECENT: ClassVar[timedelta] = timedelta(days=1)
    WINDOW_STEADY: ClassVar[timedelta] = timedelta(days=3)
    WINDOW_ANCHOR: ClassVar[timedelta] = timedelta(days=7)

    def get_ranking_value(self):
        return self.anchor


@dataclass
class ModelScoreByParam:
    param: PredictionParams
    score: ModelScore


@dataclass
class Model:
    crunch_identifier: str  # unique identifier from tournament hub
    player: Player
    name: str
    deployment_identifier: str
    scores_by_param: list[ModelScoreByParam] = Field(default_factory=list)
    overall_score: ModelScore = None

    @staticmethod
    def create(model_runner: ModelRunner):
        model_id = model_runner.model_id
        model_name = model_runner.model_name
        player_name = model_runner.infos.get('cruncher_name') or "Unknown"
        player_uid = model_runner.infos.get('cruncher_id')
        model_deployment_id = model_runner.deployment_id

        return Model(
            crunch_identifier=model_id,
            player=Player(player_uid, player_name),
            name=model_name,
            deployment_identifier=model_deployment_id,
        )

    def update_runner_info(self, model_runner: ModelRunner):
        model_name = model_runner.model_name
        player_name = model_runner.infos.get('cruncher_name') or "Unknown"
        model_deployment_id = model_runner.deployment_id

        self.name = model_name
        self.player.name = player_name
        self.deployment_identifier = model_deployment_id

    def deployment_changed(self, model_runner: ModelRunner):
        return self.deployment_identifier != model_runner.deployment_id

    def update_score(self, param: PredictionParams, score: ModelScore):

        existing = next((s for s in self.scores_by_param if s.param == param), None)
        if existing:
            existing.score = score
        else:
            self.scores_by_param.append(ModelScoreByParam(param, score))

    def calc_overall_score(self):
        if not self.scores_by_param:
            return None

        recent_scores = [param.score.recent for param in self.scores_by_param]
        steady_scores = [param.score.steady for param in self.scores_by_param]
        anchor_scores = [param.score.anchor for param in self.scores_by_param]

        self.overall_score = ModelScore(
            recent=sum(recent_scores) / len(recent_scores) if all(score is not None for score in recent_scores) else None,
            steady=sum(steady_scores) / len(steady_scores) if all(score is not None for score in steady_scores) else None,
            anchor=sum(anchor_scores) / len(anchor_scores) if all(score is not None for score in anchor_scores) else None
        )

    def qualified_name(self):
        return f"{self.player.name}/{self.name}"


@dataclass
class ModelScoreSnapshot:
    id: str
    overall_score: ModelScore
    scores_by_param: list[ModelScoreByParam]
    model_id: str
    performed_at: datetime

    MAX_HISTORY_AGE: ClassVar[timedelta] = timedelta(days=10)

    @staticmethod
    def create(model: Model, performed_at: datetime = datetime.now(timezone.utc)):
        return ModelScoreSnapshot(
            id=f"SNP_M{model.crunch_identifier}_{performed_at.strftime('%Y%m%d_%H%M%S')}",
            model_id=model.crunch_identifier,
            performed_at=performed_at,
            overall_score=model.overall_score,
            scores_by_param=model.scores_by_param
        )
