"""
DRIVER FILE FOR CREATING KNOWLEDGE BASE
"""
from src.loader import Loader


def main():
    # load the data
    kbl = Loader()
    kbl.load()
    # save the file

    kbl.create_knowledge_base()


if __name__ == '__main__':
    # run driver
    main()