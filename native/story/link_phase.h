#ifndef LINK_DONOR_PHASE_H
#define LINK_DONOR_PHASE_H
#include <math.h>

/* Preserve the parent window and sample the donor's active authored interval.
   All times are seconds. donor_span is the playable duration on its timeline;
   donor_in is the donor TimelineClip.clipIn, not its parent start time. */
static int link_project_phase(double source_in, double source_scale, double window,
                              double source_length, double donor_in, double donor_scale,
                              double donor_span, double donor_length,
                              double *clip_in, double *time_scale)
{
    if (!clip_in || !time_scale || !isfinite(source_in) || source_in < 0 ||
        !(source_scale > 0) || !(window > 0) || !(source_length > 0) ||
        !isfinite(source_length) || !isfinite(donor_in) || donor_in < 0 ||
        !(donor_scale > 0) || !(donor_span > 0) || !(donor_length > 0) ||
        !isfinite(donor_length)) return 0;
    const double end = source_in + source_scale * window;
    if (!isfinite(end)) return 0;
    double span = donor_span * donor_scale;
    if (!isfinite(span) || donor_in >= donor_length) return 0;
    span = fmin(span, donor_length - donor_in);
    const double ratio = span / source_length;
    double scale = source_scale * ratio;
    double in = donor_in + source_in * ratio;
    if (end > source_length + 1e-5) {
        /* Timeline may explicitly hold the last sprite beyond AnimationClip.length.
           Fit the remaining donor tail to that window. A wholly held window
           advances only at Unity's minimum supported TimelineClip speed. */
        const double tail = donor_in + span;
        const double remaining = fmax(0., (source_length - source_in) * ratio);
        scale = fmax(.001, remaining / window);
        in = tail - scale * window;
        if (in < donor_in - 1e-8) return 0;
        in = fmax(donor_in, in);
    }
    if (!isfinite(in) || !isfinite(scale) || scale < .001 || scale > 1000 ||
        in >= donor_length || in + window * scale > donor_length + 1e-5) return 0;
    *clip_in = in;
    *time_scale = scale;
    return 1;
}
#endif
