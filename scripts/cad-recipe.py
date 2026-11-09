#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Prepare/edit a mathematical CAD recipe, or explicitly reconstruct it locally."""
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import cad_contract
from export_transaction import write_text


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    new=sub.add_parser('create');new.add_argument('config',type=Path);new.add_argument('output',type=Path);new.add_argument('--tolerance-mm',type=float,default=.001)
    edit=sub.add_parser('edit');edit.add_argument('recipe',type=Path);edit.add_argument('changes',type=Path);edit.add_argument('output',type=Path)
    inspect=sub.add_parser('prepare');inspect.add_argument('recipe',type=Path);inspect.add_argument('output',type=Path)
    send=sub.add_parser('send');send.add_argument('recipe',type=Path);send.add_argument('--replace',help='An existing RatioLab mathematical group; preserves unrelated CAD work')
    args=parser.parse_args()
    def read(path):
        if path.stat().st_size>16*1024*1024:raise ValueError('CAD recipe file exceeds its resource limit.')
        return json.loads(path.read_text(encoding='utf-8'))
    if args.action=='create':
        data=read(args.config);result=cad_contract.create(data['family'],data.get('parameters',{}),tolerance_mm=args.tolerance_mm)
    elif args.action=='edit':result=cad_contract.edit(read(args.recipe),read(args.changes))
    elif args.action=='prepare':
        from solidcraft_recipe import compile
        result=compile(read(args.recipe))
    else:
        from connection import Client
        with Client() as client:result=client.insert_recipe(read(args.recipe),replace=args.replace)
    if hasattr(args,'output'):
        write_text(args.output,json.dumps(result,indent=2,allow_nan=False)+'\n');print(args.output.resolve())
    else:print(json.dumps(result,indent=2,allow_nan=False))


if __name__=='__main__':main()
