"""Test RRG visualization with synthetic data."""

from src.rrg.visualization import RRGVisualizer, create_rrg_chart_from_data


def test_rrg_visualization_synthetic():
    """Test RRG chart creation with synthetic data."""
    # Create synthetic RRG data matching the reference chart
    rs_ratios = [105.2, 98.5, 92.3, 104.8, 96.7, 101.5, 97.2, 94.1, 103.6, 99.4]
    rs_momentums = [102.5, 104.2, 96.8, 95.3, 108.1, 94.7, 106.5, 97.8, 103.2, 98.9]
    labels = [
        "24500 CE", "24100 PE", "24900 CE", "25200 PE", "24800 CE",
        "25100 PE", "24700 CE", "25300 PE", "25000 CE", "25400 PE"
    ]
    
    visualizer = RRGVisualizer()
    
    # Create chart
    fig = create_rrg_chart_from_data(
        rs_ratios=rs_ratios,
        rs_momentums=rs_momentums,
        labels=labels,
        title="Nifty 50 Options Strike Relative Rotation Graph (RRG) - Synthetic Test"
    )
    
    # Verify chart was created
    assert fig is not None
    assert len(fig.axes) == 1
    
    # Verify axes are set correctly
    ax = fig.axes[0]
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    
    # Should match the coordinate system (94-106)
    assert xlim[0] == 94
    assert xlim[1] == 106
    assert ylim[0] == 94
    assert ylim[1] == 106
    
    # Verify reference lines exist
    # (This is a basic visual check)
    print("✅ RRG visualization synthetic test: PASSED")
    print(f"   Chart created with {len(labels)} data points")
    print(f"   X-axis range: {xlim}")
    print(f"   Y-axis range: {ylim}")
    
    # Test quadrant summary
    from src.rrg.models import RRGSnapshot, RRGDataPoint, RRGQuadrant
    from datetime import datetime
    
    # Create synthetic snapshot
    data_points = []
    for rs_ratio, rs_momentum, label in zip(rs_ratios, rs_momentums, labels):
        # Determine quadrant
        if rs_ratio > 100 and rs_momentum > 100:
            quadrant = RRGQuadrant.LEADING
        elif rs_ratio < 100 and rs_momentum > 100:
            quadrant = RRGQuadrant.IMPROVING
        elif rs_ratio < 100 and rs_momentum < 100:
            quadrant = RRGQuadrant.LAGGING
        else:
            quadrant = RRGQuadrant.WEAKENING
        
        parts = label.split()
        strike = float(parts[0]) if parts[0].replace('.', '').isdigit() else 0
        option_type = parts[1] if len(parts) > 1 else "CE"
        
        data_points.append(RRGDataPoint(
            strike=strike,
            option_type=option_type,
            rs=0.0,
            rs_ratio=rs_ratio,
            rs_momentum=rs_momentum,
            quadrant=quadrant,
            timestamp=datetime.now(),
            option_ltp=0.0,
            benchmark_ltp=0.0,
        ))
    
    snapshot = RRGSnapshot(
        benchmark_symbol="NIFTY",
        benchmark_ltp=25000.0,
        timeframe="1min",
        timestamp=datetime.now(),
        data_points=data_points,
    )
    
    summary = visualizer.create_quadrant_summary(snapshot)
    
    # Verify quadrant summary
    assert "leading" in summary
    assert "improving" in summary
    assert "lagging" in summary
    assert "weakening" in summary
    
    print("   Quadrant summary created successfully")
    for quadrant, data in summary.items():
        print(f"   {quadrant}: {data['count']} points")


def test_quadrant_background_rendering():
    """Test that quadrant backgrounds render with correct coordinates."""
    visualizer = RRGVisualizer()
    
    # Create minimal test data
    rs_ratios = [102.0, 98.0, 96.0, 104.0]
    rs_momentums = [102.0, 104.0, 96.0, 98.0]
    labels = ["Test1", "Test2", "Test3", "Test4"]
    
    fig = create_rrg_chart_from_data(
        rs_ratios=rs_ratios,
        rs_momentums=rs_momentums,
        labels=labels,
        title="Quadrant Background Test"
    )
    
    ax = fig.axes[0]
    
    # Verify quadrant backgrounds are drawn
    # Count patches (rectangles)
    import matplotlib.patches as patches
    patches_list = [child for child in ax.get_children() if isinstance(child, patches.Rectangle)]
    
    # Should have 4 quadrant backgrounds (allowing for extra patches from matplotlib)
    assert len(patches_list) >= 4, f"Expected at least 4 quadrant backgrounds, got {len(patches_list)}"
    
    # Verify reference lines exist
    children = ax.get_children()
    lines = [child for child in children if hasattr(child, 'get_xdata')]
    x_lines = [line for line in lines if hasattr(line, 'get_xdata') and abs(line.get_xdata()[0] - 100) < 0.1]
    y_lines = [line for line in lines if hasattr(line, 'get_ydata') and abs(line.get_ydata()[0] - 100) < 0.1]
    
    assert len(x_lines) >= 1, "Should have vertical reference line at x=100"
    assert len(y_lines) >= 1, "Should have horizontal reference line at y=100"
    
    print("✅ Quadrant background rendering: PASSED")
    print(f"   Quadrant backgrounds: {len(patches_list)}")
    print(f"   Reference lines: {len(x_lines)} vertical, {len(y_lines)} horizontal")


if __name__ == "__main__":
    print("Testing RRG visualization...")
    print()
    
    test_rrg_visualization_synthetic()
    print()
    test_quadrant_background_rendering()
    
    print()
    print("="*60)
    print("✅ RRG VISUALIZATION TESTS COMPLETED")
    print("="*60)
