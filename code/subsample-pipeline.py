'''
Snakemake pipeline for running subsample analyses.

To submit from subsampling directory:
nohup snakemake -kps $ssc/code/subsample-pipeline.py -j 3600 --ri -c "qsub -l h_vmem={params.h_vmem} -l bigio={params.bigio} -N {params.name} -V -j y -cwd -o {log} -q blades.q" &
'''

import os
from string import ascii_letters

# Paths ------------------------------------------------------------------------

# All paths must end in a forward slash

# The directory to store the subsampling results
WORKING_DIR = "./"
# The directory that contains the mapping results, i.e. BAM files
SEQS_DIR = "/mnt/gluster/home/jdblischak/ssd/bam-combined/"
# The directory that contains the processed data sets
DATA_DIR = "/mnt/lustre/home/jdblischak/singleCellSeq/data/"

# Set up for subsampling directory
LOG_DIR = WORKING_DIR + "log/"
BAM_DIR = WORKING_DIR + "bam-combined/"
RMDUP_DIR = WORKING_DIR + "bam-rmdup-umi/"
COUNTS_MATRIX = WORKING_DIR + "counts-matrix/"
OUTPUT_DIR = WORKING_DIR + "output/"

# Processed data files used in analysis
GOOD_CELLS = DATA_DIR + "quality-single-cells.txt"
KEEP_GENES = DATA_DIR + "genes-pass-filter.txt"


for d in [LOG_DIR, BAM_DIR, RMDUP_DIR, OUTPUT_DIR]:
    if not os.path.isdir(d):
        os.mkdir(d)

# Variables --------------------------------------------------------------------

individuals = ["NA19098", "NA19101", "NA19239"]
depths = [50000, 250000, 500000, 1500000, 4000000]
cells = [5, 10, 15, 25, 50, 75, 125]
seeds = range(1, 10 + 1)
types = ["reads", "molecules"]
genes = ["all", "lower", "upper"]

# Targets ----------------------------------------------------------------------

# The target rules are in reverse order of the pipeline steps.

localrules: all, submit_subsampler, submit_subsampler_test

rule all:
	input: "subsampling-results.txt"

rule submit_subsampler:
    input: expand(OUTPUT_DIR + "{TYPE}-{IND}-{CELLS}-{SEED}-{DEPTH}-{GENE}.txt", \
           IND = individuals, \
           DEPTH = depths, \
           CELLS = cells, \
           SEED = seeds, \
           TYPE = types, \
           GENE = genes)

rule submit_subsampler_test:
    input: expand(OUTPUT_DIR + "{TYPE}-{IND}-{CELLS}-{SEED}-{DEPTH}-{GENE}.txt", \
           IND = individuals[0:2], \
           DEPTH = depths[0:2], \
           CELLS = cells[0:2], \
           SEED = seeds[0:2], \
           TYPE = types, \
           GENE = genes)

# Pipeline ---------------------------------------------------------------------

# Contrary to the target rules, the pipeline rules are written below
# in the order in which they are run.

rule subsampler:
	input: single_sub = COUNTS_MATRIX + "{DEPTH}-{TYPE}-raw-single-per-sample.txt",
           single_full = DATA_DIR + "molecules-raw-single-per-sample.txt",
           ercc = DATA_DIR + "expected-ercc-molecules.txt",
           bulk = DATA_DIR + "reads-raw-bulk-per-sample.txt",
           good_cells = GOOD_CELLS,
           keep_genes = KEEP_GENES
	output: all = OUTPUT_DIR + "{TYPE}-{IND}-{CELLS}-{SEED}-{DEPTH}-all.txt",
            lower = OUTPUT_DIR + "{TYPE}-{IND}-{CELLS}-{SEED}-{DEPTH}-lower.txt",
            upper = OUTPUT_DIR + "{TYPE}-{IND}-{CELLS}-{SEED}-{DEPTH}-upper.txt"
	params: cells = "{CELLS}", seed = "{SEED}",
            ind = "{IND}",
            h_vmem = '2g', bigio = '0',
            name = lambda wildcards: 'sub-' + "-".join([wildcards.IND,
                                                       wildcards.CELLS,
                                                       wildcards.SEED,
                                                       wildcards.DEPTH])
	log: LOG_DIR
	shell: "\
subsampler.R {params.cells} {params.seed} {input.single_sub} \
  {input.single_full} {input.ercc} {input.bulk} \
  --individual={params.ind} --good_cells={input.good_cells} \
  --keep_genes={input.keep_genes} -d -o {output.all}; \
\
subsampler.R {params.cells} {params.seed} {input.single_sub} \
  {input.single_full} {input.ercc} {input.bulk} \
  --individual={params.ind} --good_cells={input.good_cells} \
  --keep_genes={input.keep_genes} -d -u 0.5 -o {output.lower}; \
\
subsampler.R {params.cells} {params.seed} {input.single_sub} \
  {input.single_full} {input.ercc} {input.bulk} \
  --individual={params.ind} --good_cells={input.good_cells} \
  --keep_genes={input.keep_genes} -d -l 0.5 -o {output.upper}"

rule gather_subsample_results:
	input: expand(OUTPUT_DIR + "{TYPE}-{IND}-{CELLS}-{SEED}-{DEPTH}-{GENE}.txt", \
           IND = individuals, \
           DEPTH = depths, \
           CELLS = cells, \
           SEED = seeds, \
           TYPE = types, \
           GENE = genes)
	output: "subsampling-results.txt"
	params: h_vmem = '2g', bigio = '0',
            name = "gather-subsampling-results"
	log: LOG_DIR
	run:
           import os

           # Grab the header from the first file
           first = open(input[0])
           header = first.readline()
           first.close()

           # Create output file
           out = open(output[0], "w")
           out.write("type\tdepth\tgene_subset\t" + header)

           # Write the contents of each input file to output file
           for fname in input:
               fname_parts = os.path.basename(fname).rstrip(".txt").split("-")
               type = fname_parts[0]
               depth = fname_parts[-2]
               gene_subset = fname_parts[-1]
               f = open(fname, "r")
               f_header = f.readline()
               # Don't output results from analyses with too few cells to perform
               # subsampling.
               num_cols = len(f_header.split("\t"))
               if num_cols < 22:
                   continue
               assert f_header == header, "File %s does not have the correct header"%(fname)
               for line in f:
                   out.write(type + "\t" + depth + "\t" + gene_subset + "\t" + line)
               f.close()

           out.close()