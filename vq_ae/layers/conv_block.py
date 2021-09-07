from typing import Union, List, Optional, Tuple
from collections.abc import Iterable
from functools import partial

import torch
import numpy as np
from torch import nn
from hydra.utils import instantiate

from utils.conf_helpers import ModuleConf

# List of elements | single element | single element + repetitions
ModuleConfList = Union[List[ModuleConf], Union[ModuleConf, Tuple[ModuleConf, int]]]

class DownBlock(nn.Module):
    out_channels: int

    def __init__(
        self,
        in_channels: int,
        n_down: int,
        conv_conf: ModuleConf,
        n_pre_layers: Optional[int],
        n_post_layers: Optional[int]
    ):
        super().__init__()

        pre_layers, post_layers = [
            [{**conv_conf, **{'mode': 'same'}}] * n_layers
            for n_layers in (n_pre_layers, n_post_layers)
        ]
        self.layers = nn.Sequential(*(
            EnvelopBlock(
                envelop_conf={**conv_conf, **{'mode': 'down'}},
                in_channels=in_c,
                out_channels=out_c,
                pre_layers=pre_layers,
                post_layers=post_layers
            )
            for in_c, out_c in (
                (in_channels*(2**j), in_channels*(2**(j+1))) for j in range(n_down)
            )
        ))
        self.out_channels = in_channels * 2 ** n_down

    def forward(self, x):
        return self.layers(x)


class UpBlock(nn.Module):
    '''basically a DownBlock in reverse'''
    in_channels: int

    def __init__(
        self,
        out_channels: int,
        n_up: int,
        conv_conf: ModuleConf,
        n_pre_layers: Optional[int],
        n_post_layers: Optional[int]
    ):
        super().__init__()

        pre_layers, post_layers = [
            [{**conv_conf, **{'mode': 'same'}}] * n_layers
            for n_layers in (n_pre_layers, n_post_layers)
        ]
        self.layers = nn.Sequential(*(
            EnvelopBlock(
                envelop_conf={**conv_conf, **{'mode': 'up'}},
                in_channels=in_c,
                out_channels=out_c,
                pre_layers=pre_layers,
                post_layers=post_layers
            )
            for in_c, out_c in (
                (out_channels*(2**(j+1)), out_channels*(2**j)) for j in range(n_up-1, -1, -1)
            )
        ))
        self.in_channels = out_channels * 2 ** n_up

    def forward(self, x):
        return self.layers(x)


class EnvelopBlock(nn.Module):
    def __init__(
        self,
        envelop_conf: ModuleConf,
        in_channels: int,
        out_channels: int,
        pre_layers: Optional[ModuleConfList] = None,
        post_layers: Optional[ModuleConfList] = None
    ):
        super().__init__()

        def instantiate_layers(
            layers: Optional[ModuleConfList],
            in_channels: int,
            out_channels: int
        ) -> Iterable:

            return map(
                partial(instantiate, in_channels=in_channels, out_channels=out_channels),
                filter(None, (
                     ((layers[0] for _ in range(layers[1]))
                      if len(layers) == 2 and isinstance(layers[1], int)
                      else layers)
                     if isinstance(layers, Iterable)
                     else (layers,))
                )
            )

        self.layers = nn.Sequential(
            *instantiate_layers(pre_layers, in_channels, in_channels),
            instantiate(envelop_conf, in_channels=in_channels, out_channels=out_channels),
            *instantiate_layers(post_layers, out_channels, out_channels),
        )

    def forward(self, x):
        return self.layers(x)


class PreActFixupResBlock(nn.Module):
    # Adapted from:
    # https://github.com/hongyi-zhang/Fixup/blob/master/imagenet/models/fixup_resnet_imagenet.py#L20

    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        mode: str,
        bottleneck_divisor: int,
        activation: ModuleConf,
        conv_conf: ModuleConf,
    ):
        super().__init__()

        assert mode in ("down", "same", "up", "out")
        conv_conf = conv_conf[mode]

        branch_channels = max(max(in_channels, out_channels) // bottleneck_divisor, 1)

        self.activation = instantiate(activation)

        self.bias1a, self.bias1b, self.bias2a, self.bias2b, self.bias3a, self.bias3b, self.bias4 = (
            nn.Parameter(torch.zeros(1)) for _ in range(7)
        )
        self.scale = nn.Parameter(torch.ones(1))

        self.branch_conv1 = instantiate(
            conv_conf['branch_conv1'],
            in_channels=in_channels,
            out_channels=branch_channels
        )
        self.branch_conv2 = instantiate(
            conv_conf['branch_conv2'],
            in_channels=branch_channels,
            out_channels=branch_channels
        )
        self.branch_conv3 = instantiate(
            conv_conf['branch_conv3'],
            in_channels=branch_channels,
            out_channels=out_channels
        )

        if not (mode in ("same", "out") and in_channels == out_channels):
            self.bias1c, self.bias1d = (
                nn.Parameter(torch.zeros(1))
                for _ in range(2)
            )
            self.skip_conv = instantiate(
                conv_conf['skip_conv'],
                in_channels=in_channels,
                out_channels=out_channels
            )
        else:
            self.skip_conv = None

    def forward(self, input: torch.Tensor):
        out = input

        out = self.activation(out + self.bias1a)
        out = self.branch_conv1(out + self.bias1b)

        out = self.activation(out + self.bias2a)
        out = self.branch_conv2(out + self.bias2b)

        out = self.activation(out + self.bias3a)
        out = self.branch_conv3(out + self.bias3b)

        out = out * self.scale + self.bias4

        out = out + (
            self.skip_conv(input + self.bias1c) + self.bias1d
            if self.skip_conv is not None
            else input
        )

        return out

    @torch.no_grad()
    def initialize_weights(self, num_layers):

        # branch_conv1
        weight = self.branch_conv1.weight
        nn.init.normal_(
            weight,
            mean=0,
            std=np.sqrt(2 / (weight.shape[0] * np.prod(weight.shape[2:]))) * num_layers ** (-0.5)
        )

        # branch_conv2
        nn.init.kaiming_normal_(self.branch_conv2.weight)

        # branch_conv3
        nn.init.constant_(self.branch_conv3.weight, val=0)
        # nn.init.kaiming_normal_(self.branch_conv3.weight)

        if self.skip_conv is not None:
            nn.init.xavier_normal_(self.skip_conv.weight)
