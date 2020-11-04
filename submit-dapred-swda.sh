#!/bin/bash

#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --partition=sgpu
#SBATCH --time=20:10:00
#SBATCH --output=logs/expt-swda/run-%j.out

source /curc/sw/anaconda3/latest

conda activate hf-transformers

echo "== This is the scripting step! =="
python -u train.py --expr DAestimate
echo "== End of Job =="
