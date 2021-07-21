import argparse
import logging

import yaml

from models.alexnet import AlexNet
from models.googlenet import GoogLeNet
from models.half_plus_two import HalfPlusTwo
from models.resnet import Resnet
from models.skyline_extraction import SkylineExtraction
from models.vgg16 import VGG16

BENCH_FOLDER = "bench_data"

if __name__ == "__main__":
    # init log
    log_format = "%(asctime)s:%(levelname)s:%(name)s:" \
                 "%(filename)s:%(lineno)d:%(message)s"
    logging.basicConfig(level='INFO', format=log_format)

    parser = argparse.ArgumentParser()
    parser.add_argument("-p", default="parameters.yml", type=str)
    parser.add_argument("-o", default=None, type=str)
    args = parser.parse_args()

    with open(args.p, 'r') as file:
        params = yaml.load(file.read(), Loader=yaml.FullLoader)

    # init benchmark
    status = "init"
    logging.info(status)

    if params["model"] == "resnet":  # resnet_NHWC
        model = Resnet(args.p, "resnet", 1, logging, output_file=args.o)
    elif params["model"] == "alexnet":
        model = AlexNet(args.p, "alexnet", 1, logging, output_file=args.o)
    elif params["model"] == "googlenet":
        model = GoogLeNet(args.p, "googlenet", 1, logging, output_file=args.o)
    elif params["model"] == "vgg16":
        model = VGG16(args.p, "vgg16", 1, logging, output_file=args.o)
    elif params["model"] == "skyline-extraction":
        model = SkylineExtraction(args.p, "skyline-extraction", 1, logging, output_file=args.o)
    elif params["model"] == "half-plus-two":
        model = HalfPlusTwo(args.p, "half-plus-two", 1, logging, output_file=args.o)
    else:
        model = HalfPlusTwo(args.p, "half-plus-two", 1, logging, output_file=args.o)

    if params["profile"]:
        model.run_profiling()
    if params["benchmark"]:
        model.run_benchmark()
    if params["validate"]:
        model.validate()
