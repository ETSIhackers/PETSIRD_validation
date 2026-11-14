// Per-frame activity of singles units ("buckets") and per-crystal alive-time fractions from a PETSIRD file written by
// STIR_PETSIRD_convertor. Same structure as petsird_analysis.cpp: read the header, then loop over the time blocks.
//
// Usage:  petsird_bucket file.petsird frame_length_s n_frames dtp [module ...]
//
//   with modules   one group made of exactly those modules (e.g. bucket 76 = modules 322 and 330)
//   without        every bucket is its own group: one row per frame and bucket is written
#include "petsird/binary/protocols.h"
#include "petsird_helpers.h"
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <variant>
#include <vector>

static const int N_AXIAL_BLOCKS = 8;               // modules along the axis
static const int TRANSAXIAL_BLOCKS_PER_BUCKET = 2; // modules around the ring that make up one bucket

int
main(int argc, char const* argv[])
{
  if (argc < 5)
    {
      std::cerr << "Usage: " << argv[0] << " file.petsird frame_length_s n_frames dtp [module ...]\n"
                << "       without modules, every bucket is written\n";
      return EXIT_FAILURE;
    }
  const std::string filename = argv[1];
  const double frame_length_ms = 1000.0 * std::atof(argv[2]);
  const int n_frames = std::atoi(argv[3]);
  const double dtp = std::atof(argv[4]);
  std::vector<int> given_modules;
  for (int i = 5; i < argc; ++i)
    given_modules.push_back(std::atoi(argv[i]));

  petsird::Header header;
  {
    petsird::binary::PETSIRDReader reader(filename);
    reader.ReadHeader(header);
  }
  const auto& scanner = header.scanner;
  const int num_modules = static_cast<int>(scanner.scanner_geometry.replicated_modules[0].transforms.size());
  const std::size_t num_el = scanner.scanner_geometry.replicated_modules[0].object.detecting_elements.transforms.size();
  const std::size_t num_en = scanner.event_energy_bin_edges[0].NumberOfBins();
  const std::size_t bins_per_module = num_el * num_en;
  const std::size_t num_bins = static_cast<std::size_t>(num_modules) * bins_per_module;
  std::cerr << "modules in the scanner: " << num_modules << ", crystals per module: " << num_el << ", energy bins: " << num_en
            << "\n";

  // buckets
  if (num_modules % (N_AXIAL_BLOCKS * TRANSAXIAL_BLOCKS_PER_BUCKET) != 0)
    {
      std::cerr << num_modules << " modules do not fit the bucket layout set at the top of this file\n";
      return EXIT_FAILURE;
    }
  const int n_trans_buckets = num_modules / (N_AXIAL_BLOCKS * TRANSAXIAL_BLOCKS_PER_BUCKET);
  const int num_buckets = n_trans_buckets * N_AXIAL_BLOCKS;
  std::vector<int> bucket_of(num_modules);
  std::vector<std::vector<int>> modules_of_bucket(num_buckets);
  for (int m = 0; m < num_modules; ++m)
    {
      bucket_of[m] = (m / N_AXIAL_BLOCKS) / TRANSAXIAL_BLOCKS_PER_BUCKET + n_trans_buckets * (m % N_AXIAL_BLOCKS);
      modules_of_bucket[bucket_of[m]].push_back(m);
    }
  std::cerr << "buckets: " << num_buckets << " (" << n_trans_buckets << " transaxial x " << N_AXIAL_BLOCKS << " axial)\n";

  // groups: every bucket, or the modules given on the command line
  const bool all_buckets = given_modules.empty();
  std::vector<std::vector<int>> group_modules;
  std::vector<int> group_of(num_modules, -1);
  if (all_buckets)
    {
      group_modules = modules_of_bucket;
      for (int m = 0; m < num_modules; ++m)
        group_of[m] = bucket_of[m];
    }
  else
    {
      for (int m : given_modules)
        {
          if (m < 0 || m >= num_modules)
            {
              std::cerr << "module " << m << " is outside 0.." << num_modules - 1 << "\n";
              return EXIT_FAILURE;
            }
          group_of[m] = 0;
        }
      group_modules.push_back(given_modules);
    }
  const int n_groups = static_cast<int>(group_modules.size());

  const double alive_bytes = 8.0 * n_frames * static_cast<double>(num_bins);
  if (alive_bytes > 2e9)
    {
      std::cerr << "the alive fractions would need " << alive_bytes / 1e9 << " GB: use fewer or longer frames\n";
      return EXIT_FAILURE;
    }

  // ---------- pass 1: alive fractions of every crystal, summed over the dead-time blocks of each frame ----------
  std::vector<std::vector<double>> alive_sum(n_frames, std::vector<double>(num_bins, 0.0));
  std::vector<long> n_dead(n_frames, 0);
  long n_event_blocks = 0;
  double last_time = 0.0;
  {
    petsird::binary::PETSIRDReader reader(filename);
    petsird::Header dummy;
    reader.ReadHeader(dummy);
    petsird::TimeBlock time_block;
    while (reader.ReadTimeBlocks(time_block))
      {
        if (std::holds_alternative<petsird::EventTimeBlock>(time_block))
          {
            last_time = std::get<petsird::EventTimeBlock>(time_block).time_interval.stop;
            ++n_event_blocks;
          }
        else if (std::holds_alternative<petsird::DeadTimeTimeBlock>(time_block))
          {
            const auto& blk = std::get<petsird::DeadTimeTimeBlock>(time_block);
            const double mid = 0.5 * (static_cast<double>(blk.time_interval.start) + static_cast<double>(blk.time_interval.stop));
            const int f = static_cast<int>(mid / frame_length_ms);
            const auto& sat = blk.alive_time_fractions.singles_alive_time_fractions;
            if (f < 0 || f >= n_frames || sat.empty())
              continue;
            const auto& fractions = sat[0];
            if (fractions.size() != num_bins)
              {
                std::cerr << "a dead-time block has " << fractions.size() << " values, but " << num_modules << " modules x "
                          << num_el << " crystals x " << num_en << " energy bins = " << num_bins << " are expected\n";
                return EXIT_FAILURE;
              }
            for (std::size_t b = 0; b < num_bins; ++b)
              alive_sum[f][b] += fractions[b];
            ++n_dead[f];
          }
      }
  }
  std::cerr << "event time blocks: " << n_event_blocks << ", last time block at " << last_time << " ms\n";

  // frame means
  std::vector<std::vector<float>> alive(n_frames);
  for (int f = 0; f < n_frames; ++f)
    if (n_dead[f] > 0)
      {
        alive[f].resize(num_bins);
        for (std::size_t b = 0; b < num_bins; ++b)
          alive[f][b] = static_cast<float>(alive_sum[f][b] / n_dead[f]);
      }
  alive_sum.clear();
  alive_sum.shrink_to_fit();

  // is the alive fraction stored per crystal? (if every crystal of a module has the same value, it is still per module/bucket)
  double max_range_within_module = 0.0;
  for (int f = 0; f < n_frames; ++f)
    {
      if (alive[f].empty())
        continue;
      for (int m = 0; m < num_modules; ++m)
        {
          const auto first = alive[f].begin() + m * bins_per_module;
          const auto mm = std::minmax_element(first, first + bins_per_module);
          max_range_within_module = std::max(max_range_within_module, static_cast<double>(*mm.second - *mm.first));
        }
    }
  std::cerr << "largest alive-fraction range among the crystals of one module: " << max_range_within_module
            << " (0 = one value per module, i.e. not stored per crystal)\n";

  // ---------- pass 2: count the events, each divided by the alive fractions of its two crystals ----------
  const std::size_t tally_size = static_cast<std::size_t>(n_frames) * n_groups;
  std::vector<double> prompts(tally_size, 0.0), delayeds(tally_size, 0.0), prompts_pair(tally_size, 0.0),
      delayeds_pair(tally_size, 0.0), net_sum(tally_size, 0.0), net_alive(tally_size, 0.0);
  auto index = [&](int f, int g) { return static_cast<std::size_t>(f) * n_groups + g; };

  // sign is +1 for a prompt and -1 for a delayed (net counts = prompts - delayeds)
  auto count_event = [&](const petsird::CoincidenceEvent& event, int f, bool is_delayed) {
    const std::size_t bin[2] = { event.detection_bins[0], event.detection_bins[1] };
    const double a[2] = { alive[f][bin[0]], alive[f][bin[1]] };
    const int g[2] = { group_of[bin[0] / bins_per_module], group_of[bin[1] / bins_per_module] };
    const double pair_correction = 1.0 / (a[0] * a[1]);
    for (int end = 0; end < 2; ++end)
      {
        if (g[end] < 0)
          continue;
        if (end == 1 && g[1] == g[0]) // an event with both ends in the same group is counted once
          continue;
        const std::size_t i = index(f, g[end]);
        const double partner_alive = a[1 - end];
        if (is_delayed)
          {
            delayeds[i] += 1;
            delayeds_pair[i] += pair_correction;
            net_sum[i] -= 1;
            net_alive[i] -= partner_alive;
          }
        else
          {
            prompts[i] += 1;
            prompts_pair[i] += pair_correction;
            net_sum[i] += 1;
            net_alive[i] += partner_alive;
          }
      }
  };

  {
    petsird::binary::PETSIRDReader reader(filename);
    petsird::Header dummy;
    reader.ReadHeader(dummy);
    petsird::TimeBlock time_block;
    while (reader.ReadTimeBlocks(time_block))
      {
        if (!std::holds_alternative<petsird::EventTimeBlock>(time_block))
          continue;
        const auto& blk = std::get<petsird::EventTimeBlock>(time_block);
        const double mid = 0.5 * (static_cast<double>(blk.time_interval.start) + static_cast<double>(blk.time_interval.stop));
        const int f = static_cast<int>(mid / frame_length_ms);
        if (f < 0 || f >= n_frames || alive[f].empty())
          continue;
        for (const auto& event : blk.prompt_events[0][0])
          count_event(event, f, false);
        if (!blk.delayed_events.empty())
          for (const auto& event : blk.delayed_events[0][0])
            count_event(event, f, true);
      }
  }

  // ---------- output ----------
  std::cout.precision(10);
  if (all_buckets)
    std::cout << "frame,bucket,transaxial,axial,";
  else
    std::cout << "frame,";
  std::cout << "prompts,delayeds,mean_alive,alive_min,alive_max,mean_rate,dead_time_blocks,prompts_pair,delayeds_pair,"
               "mean_partner_alive\n";

  for (int f = 0; f < n_frames; ++f)
    {
      if (alive[f].empty())
        continue;
      for (int g = 0; g < n_groups; ++g)
        {
          double a_mean = 0.0;
          double a_min = std::numeric_limits<double>::max(), a_max = 0.0;
          for (int m : group_modules[g])
            for (std::size_t b = m * bins_per_module; b < (m + 1) * bins_per_module; ++b)
              {
                a_mean += alive[f][b];
                a_min = std::min<double>(a_min, alive[f][b]);
                a_max = std::max<double>(a_max, alive[f][b]);
              }
          a_mean /= static_cast<double>(group_modules[g].size() * bins_per_module);
          const std::size_t i = index(f, g);
          std::cout << f + 1 << ",";
          if (all_buckets)
            std::cout << g << "," << g % n_trans_buckets << "," << g / n_trans_buckets << ",";
          std::cout << prompts[i] << "," << delayeds[i] << "," << a_mean << "," << a_min << "," << a_max << ","
                    << 2.0 * std::log(a_mean) / dtp << "," << n_dead[f] << "," << prompts_pair[i] << "," << delayeds_pair[i]
                    << "," << (net_sum[i] != 0 ? net_alive[i] / net_sum[i] : 0.0) << "\n";
        }
    }
  return EXIT_SUCCESS;
}
