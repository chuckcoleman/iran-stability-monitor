#!/usr/bin/env python3
"""One-shot Sunday orchestration OUTSIDE GitHub: review first, submit second.

Designed for an external scheduler on a trusted host, never GitHub Actions.
Only after BOTH clean reviews and full validation may GitHub be contacted.
Neither failures nor timeouts ever count as permission to submit/publish.
"""
import argparse
from pathlib import Path
import sys

import pre_github_review
import submit_reviewed_assessment


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",required=True,
                        help="NEW output directory outside the GitHub checkout")
    parser.add_argument("--submit",action="store_true",
                        help="After clean review, submit a protected PR")
    parser.add_argument("--merge",action="store_true",
                        help="After clean review and PR CI, merge without bypass")
    args=parser.parse_args(argv)
    if args.merge and not args.submit:
        parser.error("--merge requires --submit")
    # Any local review error or time limit stops execution here.
    approved=pre_github_review.prepare(Path(args.output_dir))
    if not args.submit:
        print("Outside-GitHub dual review and validation complete; no GitHub submission requested.")
        return 0
    submit_reviewed_assessment.submit(approved,merge=args.merge)
    return 0


if __name__=="__main__":
    sys.exit(main())
