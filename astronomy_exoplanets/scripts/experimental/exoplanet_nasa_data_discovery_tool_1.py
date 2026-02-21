#!/usr/bin/env python3
"""
FORGETTING ENGINE - REAL KEPLER DATA ANALYSIS
Downloads actual NASA light curves and runs FE algorithm
Derek Angell - CONEXUS Global Arts Media
"""

import numpy as np
import pandas as pd
from astropy.timeseries import BoxLeastSquares
import lightkurve as lk
import json
from datetime import datetime

print("="*80)
print("FORGETTING ENGINE × REAL NASA KEPLER DATA")
print("="*80)

# ============================================================================
# STEP 1: Download Real Light Curves from NASA MAST
# ============================================================================

def download_kepler_lightcurve(koi_name, max_quarters=4):
    """
    Download actual Kepler light curve from NASA MAST archive
    
    Args:
        koi_name: KOI identifier (e.g., 'KOI-7.01')
        max_quarters: Number of quarters to download (limit for speed)
    
    Returns:
        LightCurve object with real photometry data
    """
    print(f"\nDownloading {koi_name} from NASA MAST...")
    
    try:
        # Search for the target
        search_result = lk.search_lightcurve(koi_name, mission='Kepler')
        
        if len(search_result) == 0:
            print(f"  ✗ No data found for {koi_name}")
            return None
        
        # Download light curves (limit quarters for speed)
        lc_collection = search_result[:max_quarters].download_all()
        
        if lc_collection is None or len(lc_collection) == 0:
            print(f"  ✗ Download failed for {koi_name}")
            return None
        
        # Stitch quarters together
        lc = lc_collection.stitch()
        
        # Remove NaN values and outliers
        lc = lc.remove_nans().remove_outliers(sigma=5)
        
        print(f"  ✓ Downloaded {len(lc.time)} data points")
        print(f"  Duration: {(lc.time[-1] - lc.time[0]).value:.1f} days")
        
        return lc
        
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return None


# ============================================================================
# STEP 2: Run Traditional BLS (Baseline)
# ============================================================================

def run_bls_search(lc, min_period=0.5, max_period=20, n_periods=5000):
    """
    Run Box Least Squares transit search on light curve
    
    Returns:
        List of BLS candidates with periods, depths, and powers
    """
    print("\n  Running BLS transit search...")
    
    # Prepare data for BLS
    time = lc.time.value
    flux = lc.flux.value
    flux_err = lc.flux_err.value if hasattr(lc, 'flux_err') else np.ones_like(flux) * 0.001
    
    # Create BLS model
    durations = np.linspace(0.05, 0.3, 10)  # Transit durations to test (days)
    
    model = BoxLeastSquares(time, flux, dy=flux_err)
    
    # Run periodogram
    results = model.autopower(
        durations,
        minimum_period=min_period,
        maximum_period=max_period,
        frequency_factor=1.0
    )
    
    # Find top candidates
    candidates = []
    
    # Get top 50 peaks
    sorted_indices = np.argsort(results.power)[::-1][:50]
    
    for i, idx in enumerate(sorted_indices):
        period = results.period[idx].value
        power = results.power[idx]
        depth = results.depth[idx]
        duration = results.duration[idx].value
        
        candidates.append({
            'rank': i + 1,
            'period': period,
            'power': float(power),
            'depth_ppm': float(depth * 1e6),  # Convert to ppm
            'duration_hours': float(duration * 24),
            'bls_score': float(power)
        })
    
    print(f"  ✓ Found {len(candidates)} BLS candidates")
    
    return candidates


# ============================================================================
# STEP 3: Run Forgetting Engine Algorithm
# ============================================================================

def compute_coherence_f1(candidate):
    """Coherence metric: normalized BLS power"""
    return min(candidate['power'], 1.0)


def compute_anomaly_f2(candidate, candidates_list):
    """
    Anomaly metric: how unusual is this candidate?
    Measures deviation from typical transit characteristics
    """
    all_depths = [c['depth_ppm'] for c in candidates_list]
    all_durations = [c['duration_hours'] for c in candidates_list]
    
    depth_mean = np.mean(all_depths)
    depth_std = np.std(all_depths)
    duration_mean = np.mean(all_durations)
    duration_std = np.std(all_durations)
    
    # Z-score deviation
    depth_zscore = abs((candidate['depth_ppm'] - depth_mean) / (depth_std + 1e-6))
    duration_zscore = abs((candidate['duration_hours'] - duration_mean) / (duration_std + 1e-6))
    
    # Anomaly is how "weird" the signal is
    anomaly = depth_zscore + duration_zscore
    
    return float(anomaly)


def compute_paradox_score(f1, f2):
    """
    Paradox score: high coherence AND high anomaly
    P(c) = (f1 × |f2|) / (f1 + |f2| + ε)
    """
    epsilon = 1e-6
    return (f1 * abs(f2)) / (f1 + abs(f2) + epsilon)


def run_forgetting_engine(candidates, n_generations=50, population_size=50, forget_rate=0.3):
    """
    Run Forgetting Engine on BLS candidates
    
    Returns:
        List of paradoxical discoveries
    """
    print("\n  Running Forgetting Engine...")
    
    # Compute multi-objective fitness for all candidates
    for c in candidates:
        c['f1_coherence'] = compute_coherence_f1(c)
        c['f2_anomaly'] = compute_anomaly_f2(c, candidates)
        c['paradox_score'] = compute_paradox_score(c['f1_coherence'], c['f2_anomaly'])
    
    # Strategic elimination with paradox retention
    paradox_buffer = []
    
    for gen in range(n_generations):
        # Sort by composite fitness
        candidates_sorted = sorted(
            candidates, 
            key=lambda c: 0.4*c['f1_coherence'] + 0.3*c['f2_anomaly'],
            reverse=True
        )
        
        # Bottom 30% candidates for potential elimination
        n_eliminate = int(len(candidates_sorted) * forget_rate)
        bottom_candidates = candidates_sorted[-n_eliminate:]
        
        # Check paradox scores
        for c in bottom_candidates:
            if (c['paradox_score'] > 0.35 and 
                c['f1_coherence'] > 0.25 and 
                c['f2_anomaly'] > 1.0):
                
                # Retain in paradox buffer
                if c not in paradox_buffer:
                    paradox_buffer.append(c)
    
    # Sort paradox buffer by paradox score
    paradoxical_discoveries = sorted(
        paradox_buffer, 
        key=lambda c: c['paradox_score'], 
        reverse=True
    )
    
    print(f"  ✓ Found {len(paradoxical_discoveries)} paradoxical candidates")
    
    return paradoxical_discoveries[:10]  # Return top 10


# ============================================================================
# STEP 4: Main Analysis Pipeline
# ============================================================================

def analyze_target(koi_name):
    """
    Complete analysis pipeline for one target
    """
    print(f"\n{'='*80}")
    print(f"ANALYZING: {koi_name}")
    print(f"{'='*80}")
    
    # 1. Download light curve
    lc = download_kepler_lightcurve(koi_name, max_quarters=4)
    
    if lc is None:
        return None
    
    # 2. Run BLS
    bls_candidates = run_bls_search(lc)
    
    # 3. Run Forgetting Engine
    fe_discoveries = run_forgetting_engine(bls_candidates)
    
    # 4. Compare results
    print(f"\n{'='*80}")
    print(f"RESULTS FOR {koi_name}")
    print(f"{'='*80}")
    
    print(f"\nBLS Top Candidate:")
    if len(bls_candidates) > 0:
        top_bls = bls_candidates[0]
        print(f"  Period: {top_bls['period']:.3f} days")
        print(f"  Depth: {top_bls['depth_ppm']:.1f} ppm")
        print(f"  BLS Power: {top_bls['power']:.3f}")
    
    print(f"\nFE Paradoxical Discoveries:")
    for i, disc in enumerate(fe_discoveries[:3], 1):
        print(f"\n  Discovery #{i}:")
        print(f"    Period: {disc['period']:.3f} days")
        print(f"    Depth: {disc['depth_ppm']:.1f} ppm")
        print(f"    Paradox Score: {disc['paradox_score']:.4f}")
        print(f"    Coherence (f₁): {disc['f1_coherence']:.3f}")
        print(f"    Anomaly (f₂): {disc['f2_anomaly']:.3f}")
    
    return {
        'koi_name': koi_name,
        'n_datapoints': len(lc.time),
        'bls_top_candidate': bls_candidates[0] if len(bls_candidates) > 0 else None,
        'fe_discoveries': fe_discoveries
    }


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    
    # Test targets - mix of known planets and interesting false positives
    test_targets = [
        'KOI-7.01',      # Kepler-4b - known hot Jupiter
        'KOI-94.01',     # Kepler-89b - known multi-planet system
        'KOI-2124.01',   # Interesting false positive
    ]
    
    all_results = []
    
    for target in test_targets:
        result = analyze_target(target)
        if result:
            all_results.append(result)
    
    # Save results
    output_file = 'fe_real_kepler_results.json'
    
    output_data = {
        'timestamp': datetime.now().isoformat(),
        'algorithm': 'Forgetting Engine v1.0',
        'data_source': 'NASA MAST Kepler Archive',
        'targets_analyzed': len(all_results),
        'results': all_results
    }
    
    with open(output_file, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    print(f"\n{'='*80}")
    print(f"ANALYSIS COMPLETE")
    print(f"{'='*80}")
    print(f"\nResults saved to: {output_file}")
    print(f"Targets analyzed: {len(all_results)}")
    print(f"\nThis is REAL NASA data analysis!")
