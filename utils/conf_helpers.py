from typing import Union, Any
from dataclasses import dataclass
from abc import ABC

from hydra.utils import instantiate
from omegaconf import DictConfig, ListConfig, MISSING


@dataclass
class DatasetConf(ABC):
    _target_: str = 'torch.utils.data.Dataset'

@dataclass
class DataloaderConf:
    _target_: str = 'torch.utils.data.DataLoader'

    dataset: DatasetConf = MISSING

    batch_size: int = 32
    shuffle: bool = True
    num_workers: int = 6
    pin_memory: bool = True
    drop_last: bool = True
    prefetch_factor: int = 2
    persistent_workers: bool = True

@dataclass
class OptimizerConf(ABC):
    _target_: str = 'torch.optim.Optimizer'

@dataclass
class LossFConf(ABC):
    _target_: str = 'torch.nn.Module'



def instantiate_nested_conf(**nested_conf):
    '''
    Warning:
    set `_recursive_: False`
    at the same level as `_target_: utils.conf_helpers.instantiate_nested_conf`
    inside your config!
    '''
    de_nested = listify_nested_conf(nested_conf)

    if isinstance(de_nested, ListConfig):
        if len(de_nested) == 1:
            de_nested = de_nested[0]
        else:
            raise RuntimeError("This shouldn't happen")

    return instantiate(de_nested)


def listify_nested_conf(conf: Any) -> Union[DictConfig, ListConfig]:
    '''
    Given the keys and values of a nested config,
    removes keys and makes their corresponding value a ListConfig,
    if the nest level doesn't contain the key `_target_`.

    Example input:
    ```
    compose:
        transforms:
            random_crop:
                _target_: albumentations.RandomCrop
                width: 128
                height: 128
            to_tensor_v2:
                _target_: albumentations.pytorch.transforms.ToTensorV2
        _target_: albumentations.Compose
    ```
    Example output:
    ```
    - transforms:
        - _target_: albumentations.RandomCrop
          width: 128
          height: 128
        - _target: albumentations.pytorch.transforms.ToTensorV2
      _target_: albumentations.Compose
    ```
    '''

    if isinstance(conf, (DictConfig, dict)):
        return (
            listify_nested_conf(ListConfig(list(conf.values())))
            if '_target_' not in conf.keys()
            else DictConfig({
                key: listify_nested_conf(value)
                for key, value in conf.items()
            })
        )
    elif isinstance(conf, (ListConfig, list)):
        return ListConfig([
            listify_nested_conf(value)
            for value in conf
        ])
    else:
        return conf




if __name__ == '__main__':
    conf = {
        'compose': {
            'transforms': {
                'random_crop': {
                    '_target_': 'albumentations.RandomCrop',
                    'width': 128,
                    'height': 128,
                },
                'to_tensor_v2': {
                    '_target_': 'albumentations.pytorch.transforms.ToTensorV2'
                }
            },
            '_target_': 'albumentations.Compose'
        }
    }
    print(listify_nested_conf(conf))