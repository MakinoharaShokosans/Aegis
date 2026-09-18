import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DirectoryPickerModal } from '../DirectoryPickerModal';
import { fileApi } from '@/api';

describe('DirectoryPickerModal', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders directory browser with breadcrumbs and subfolders', async () => {
    vi.spyOn(fileApi, 'browseDirectories').mockResolvedValue({
      current_path: '/home/Skualeilu/Projects',
      parent_path: '/home/Skualeilu',
      is_root: false,
      directories: [
        { name: 'Aegis', path: '/home/Skualeilu/Projects/Aegis', is_directory: true },
        { name: 'EyesPro', path: '/home/Skualeilu/Projects/EyesPro', is_directory: true },
      ],
      quick_locations: [
        { label: '项目目录', path: '/home/Skualeilu/Projects' },
        { label: '用户主目录', path: '/home/Skualeilu' },
      ],
    });

    const handleSelect = vi.fn();
    const handleClose = vi.fn();

    render(
      <DirectoryPickerModal
        isOpen={true}
        initialPath="/home/Skualeilu/Projects"
        onSelect={handleSelect}
        onClose={handleClose}
      />
    );

    expect(await screen.findByText('Aegis')).toBeInTheDocument();
    expect(screen.getByText('EyesPro')).toBeInTheDocument();
    expect(screen.getByText('项目目录')).toBeInTheDocument();

    // Click on EyesPro
    fireEvent.click(screen.getByText('EyesPro'));

    // Confirm selection
    const confirmBtn = screen.getByText('选择此目录作为工作区');
    fireEvent.click(confirmBtn);

    expect(handleSelect).toHaveBeenCalledWith(
      '/home/Skualeilu/Projects/EyesPro',
      'EyesPro'
    );
  });
});
