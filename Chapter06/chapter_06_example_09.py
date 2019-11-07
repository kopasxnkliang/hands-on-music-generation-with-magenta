"""
TODO how to stats artists
"""
import argparse
import copy
import math
import os
import random
import shutil
import timeit
from itertools import cycle
from multiprocessing import Manager
from multiprocessing.pool import Pool
from typing import List, Optional

import matplotlib.pyplot as plt
import tables
from pretty_midi import PrettyMIDI, Instrument

from lakh_utils import get_msd_score_matches, get_midi_path, \
  get_matched_midi_md5
from lakh_utils import msd_id_to_h5
from threading_utils import Counter

parser = argparse.ArgumentParser()
parser.add_argument("--sample_size", type=int, default=1000)
parser.add_argument("--path_dataset_dir", type=str, required=True)
parser.add_argument("--path_match_scores_file", type=str, required=True)
parser.add_argument("--path_output_dir", type=str, required=True)
args = parser.parse_args()

MSD_SCORE_MATCHES = get_msd_score_matches(args.path_match_scores_file)


def extract_drums(msd_id: str) -> Optional[PrettyMIDI]:
  os.makedirs(args.path_output_dir, exist_ok=True)
  midi_md5 = get_matched_midi_md5(msd_id, MSD_SCORE_MATCHES)
  midi_path = get_midi_path(msd_id, midi_md5, "matched", args.path_dataset_dir)
  pm = PrettyMIDI(midi_path)
  pm_drums = copy.deepcopy(pm)
  pm_drums.instruments = [instrument for instrument in pm_drums.instruments
                          if instrument.is_drum]
  if len(pm_drums.instruments) > 1:
    # Some drum tracks are split, we can merge them
    drums = Instrument(program=0, is_drum=True)
    for instrument in pm_drums.instruments:
      for note in instrument.notes:
        drums.notes.append(note)
    pm_drums.instruments = [drums]
  if len(pm_drums.instruments) != 1:
    raise Exception(f"Invalid number of drums {msd_id}: "
                    f"{len(pm_drums.instruments)}")
  return pm_drums


def get_bd_on_beats(pm_drums: PrettyMIDI) -> float:
  beats = pm_drums.get_beats()
  bass_drums = [note.start for note in pm_drums.instruments[0].notes
                if note.pitch == 35 or note.pitch == 36]
  bass_drums_on_beat = []
  for beat in beats:
    beat_has_bass_drum = False
    for bass_drum in bass_drums:
      if math.isclose(beat, bass_drum):
        beat_has_bass_drum = True
        break
    bass_drums_on_beat.append(True if beat_has_bass_drum else False)
  num_bass_drums_on_beat = len([bd for bd in bass_drums_on_beat if bd])
  bd_on_beats = (num_bass_drums_on_beat / len(bass_drums_on_beat) * 100)
  return bd_on_beats


def process(msd_id: str, counter: Counter) -> Optional[dict]:
  try:
    with tables.open_file(msd_id_to_h5(msd_id, args.path_dataset_dir)) as h5:
      pm_drums = extract_drums(msd_id)
      bd_on_beats = get_bd_on_beats(pm_drums)
      if bd_on_beats > 70:
        # TODO move write in other example too to match method content
        pm_drums.write(os.path.join(args.path_output_dir, f"{msd_id}.mid"))
      else:
        raise Exception(f"Not on beat {msd_id}: {bd_on_beats}")
      return {"msd_id": msd_id,
              "pm_drums": pm_drums,
              "bd_on_beats": bd_on_beats}
  except Exception as e:
    print(f"Exception during processing of {msd_id}: {e}")
    return
  finally:
    counter.increment()


def app(msd_ids: List[str]):
  start = timeit.default_timer()

  # TODO cleanup
  shutil.rmtree(args.path_output_dir, ignore_errors=True)

  # TODO info
  with Pool(4) as pool:
    manager = Manager()
    counter = Counter(manager, len(msd_ids))
    print("START")
    results = pool.starmap(process, zip(msd_ids, cycle([counter])))
    results = [result for result in results if result]
    print("END")
    results_percentage = len(results) / len(msd_ids) * 100
    print(f"Number of tracks: {len(MSD_SCORE_MATCHES)}, "
          f"number of tracks in sample: {len(msd_ids)}, "
          f"number of results: {len(results)} "
          f"({results_percentage}%)")

  # TODO histogram
  pm_drums = [result["pm_drums"] for result in results]
  pm_drums_lengths = [pm.get_end_time() for pm in pm_drums]
  plt.hist(pm_drums_lengths, bins=100)
  plt.ylabel('length (sec)')
  plt.title('Drums lengths')
  plt.show()

  bd_on_beats = [result["bd_on_beats"] for result in results]
  plt.hist(bd_on_beats, bins=100)
  plt.ylabel('percentage')
  plt.title('Bass drum on beat')
  plt.show()

  stop = timeit.default_timer()
  print("Time: ", stop - start)


if __name__ == "__main__":
  if args.sample_size:
    # Process a sample of it
    MSD_IDS = random.sample(list(MSD_SCORE_MATCHES), args.sample_size)
  else:
    # Process all the dataset
    MSD_IDS = list(MSD_SCORE_MATCHES)
  app(MSD_IDS)
