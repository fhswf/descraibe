from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from huggingface_hub import hf_hub_download

from backend.vendor.facemoe.backbones import get_model


class FaceMoERecognizer:
    """
    FaceMoE-basierte Gesichtserkennung.

    Verwendet:
    - FaceMoE Swin-B
    - BRIAR-Checkpoint
    - 3 Experten
    - Top-2-Routing
    - 512-d Embeddings

    Die FaceMoE-Modellarchitektur liegt als MIT-lizenzierter
    Drittanbieter-Code unter backend/vendor/facemoe/.

    Die Modellgewichte werden bei Bedarf von Hugging Face geladen.

    Embeddings werden ausschließlich im RAM erzeugt und
    von dieser Klasse niemals gespeichert.
    """

    REPO_ID = "kartiknarayan/FaceMoE"

    CHECKPOINT_FILENAME = (
        "swin4m_exp_3_k_2_briar_full/model.pt"
    )

    IMAGE_SIZE = 120
    EMBEDDING_SIZE = 512

    NUM_EXPERTS = 3
    TOP_K = 2

    USE_FLIP_TEST = False

    def __init__(
        self,
        model_root: str | Path,
        device: str | None = None,
    ) -> None:

        self.model_root = Path(
            model_root
        )

        self.model_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        # -----------------------------------------------------
        # Gerät
        # -----------------------------------------------------

        if device is None:
            device = (
                "cuda"
                if torch.cuda.is_available()
                else "cpu"
            )

        if device == "cuda":

            if not torch.cuda.is_available():
                raise RuntimeError(
                    "CUDA wurde angefordert, "
                    "ist aber für PyTorch nicht verfügbar."
                )

            self.device = torch.device(
                "cuda"
            )

        elif device == "cpu":

            self.device = torch.device(
                "cpu"
            )

        else:

            raise ValueError(
                "device muss 'cuda' oder 'cpu' sein."
            )

        # -----------------------------------------------------
        # Checkpoint
        # -----------------------------------------------------

        weights_dir = (
            self.model_root
            / "weights"
        )

        weights_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        checkpoint_path = Path(
            hf_hub_download(
                repo_id=self.REPO_ID,
                filename=self.CHECKPOINT_FILENAME,
                local_dir=weights_dir,
            )
        )

        # -----------------------------------------------------
        # Modell
        # -----------------------------------------------------

        self.model = get_model(
            "swin_moe",
            dropout=0.0,
            fp16=False,
            num_features=self.EMBEDDING_SIZE,
            num_experts=self.NUM_EXPERTS,
            k=self.TOP_K,
        )

        # -----------------------------------------------------
        # Gewichte
        # -----------------------------------------------------

        try:
            checkpoint = torch.load(
                checkpoint_path,
                map_location="cpu",
                weights_only=True,
            )

        except TypeError:
            checkpoint = torch.load(
                checkpoint_path,
                map_location="cpu",
            )

        if (
            isinstance(checkpoint, dict)
            and "state_dict" in checkpoint
        ):
            state_dict = checkpoint[
                "state_dict"
            ]
        else:
            state_dict = checkpoint

        if not isinstance(
            state_dict,
            dict,
        ):
            raise RuntimeError(
                "Der FaceMoE-Checkpoint enthält "
                "kein gültiges State-Dict."
            )

        if (
            state_dict
            and all(
                key.startswith("module.")
                for key in state_dict
            )
        ):
            state_dict = {
                key[len("module."):]: value
                for key, value
                in state_dict.items()
            }

        self.model.load_state_dict(
            state_dict,
            strict=True,
        )

        self.model.to(
            self.device
        )

        self.model.eval()

        print(
            "FaceMoE läuft auf: "
            f"{self.device.type}"
        )

    def _preprocess(
        self,
        image: np.ndarray,
    ) -> torch.Tensor:

        if (
            image is None
            or image.size == 0
        ):
            raise ValueError(
                "Ungültiger Face-Crop."
            )

        resized = cv2.resize(
            image,
            (
                self.IMAGE_SIZE,
                self.IMAGE_SIZE,
            ),
            interpolation=cv2.INTER_LINEAR,
        )

        rgb = cv2.cvtColor(
            resized,
            cv2.COLOR_BGR2RGB,
        )

        data = (
            rgb.astype(np.float32)
            / 255.0
        )

        data = (
            data - 0.5
        ) / 0.5

        data = np.transpose(
            data,
            (2, 0, 1),
        )

        data = np.expand_dims(
            np.ascontiguousarray(
                data
            ),
            axis=0,
        )

        return (
            torch.from_numpy(
                data
            )
            .to(
                self.device
            )
        )

    def extract_embedding(
        self,
        aligned_face: np.ndarray,
    ) -> np.ndarray:

        model_input = (
            self._preprocess(
                aligned_face
            )
        )

        with torch.inference_mode():

            feature = self.model(
                model_input
            )

            feature = F.normalize(
                feature,
                p=2,
                dim=1,
            )

            if self.USE_FLIP_TEST:

                flipped_input = torch.flip(
                    model_input,
                    dims=[3],
                )

                flipped_feature = self.model(
                    flipped_input
                )

                flipped_feature = F.normalize(
                    flipped_feature,
                    p=2,
                    dim=1,
                )

                feature = F.normalize(
                    feature
                    + flipped_feature,
                    p=2,
                    dim=1,
                )

        embedding = (
            feature[0]
            .detach()
            .cpu()
            .numpy()
            .astype(np.float32)
        )

        if embedding.shape != (
            self.EMBEDDING_SIZE,
        ):
            raise RuntimeError(
                "Unerwartete FaceMoE-"
                "Embedding-Größe: "
                f"{embedding.shape}"
            )

        if not np.all(
            np.isfinite(
                embedding
            )
        ):
            raise RuntimeError(
                "FaceMoE erzeugte ein "
                "ungültiges Embedding."
            )

        return embedding

    def synchronize(
        self,
    ) -> None:

        if self.device.type == "cuda":
            torch.cuda.synchronize()

    def close(
        self,
    ) -> None:

        if hasattr(
            self,
            "model",
        ):
            del self.model

        if self.device.type == "cuda":
            torch.cuda.empty_cache()