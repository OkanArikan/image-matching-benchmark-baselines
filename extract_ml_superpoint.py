import os
import h5py
from tqdm import tqdm
import matplotlib.pyplot as plt
import numpy as np
import cv2
import torch
import torch.nn.functional as F
import argparse
import sys
import yaml
from copy import deepcopy
torch.set_default_tensor_type(torch.FloatTensor)

def str2bool(v):
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False

def save_h5(dict_to_save, filename):
    """Saves dictionary to hdf5 file"""

    with h5py.File(filename, 'w') as f:
        for key in dict_to_save:
            f.create_dataset(key, data=dict_to_save[key])

sys.path.insert(0, f'{os.getcwd()}/third_party/superpoint_forked')
from superpoint import SuperPointFrontend
import kornia as K
# data loading



def convert_imc(kps, resps):
    keypoints = kps.reshape(-1, 2)
    nkp = len(keypoints)
    scales = np.ones((nkp, 1)).astype(np.float32)
    angles =  np.zeros((nkp, 1)).astype(np.float32)
    responses = resps.reshape(-1, 1)
    return keypoints, scales, angles, responses


def extract_features(img_fname, superpoint, device, MAX_KP, max_size, norm_desc):
    img = cv2.cvtColor(cv2.imread(img_fname), cv2.COLOR_BGR2RGB)
    timg = K.image_to_tensor(img, False).float()/255.
    timg = timg.to(device)
    timg = K.color.rgb_to_grayscale(timg)
    H, W = timg.shape[2:]
    if max_size>0:
        if max_size % 16 != 0:
            max_size = int(max_size - (max_size % 16))
        min_size = int(min(H, W) * max_size / float(max(H, W)))
        if min_size % 16 !=0:
            min_size = int(min_size - (min_size % 16))
        if H > W:
            out_size = (max_size, min_size)
        else:
            out_size = (min_size, max_size)
        with torch.no_grad():
            timg_res = K.geometry.resize(timg, out_size)
    else:
        timg_res = timg
    with torch.no_grad():
        H2, W2 = timg_res.shape[2:]
        coef_h = (H/float(H2))
        coef_w = (W/float(W2))
        kp1, descs1, heatmap1 = superpoint.run(timg_res[0,0].detach().cpu().numpy())
        kp1, descs1, heatmap1 = torch.from_numpy(kp1), torch.from_numpy(descs1), torch.from_numpy(heatmap1)
        coord_1 = kp1.T
        score_1 = deepcopy(coord_1[:, 2])
        coord_1 = deepcopy(coord_1[:, :2])
        desc1 = descs1.T
        if norm_desc:
            desc1 = F.normalize(desc1, dim=1, p=2)
        score_1 = score_1.reshape(-1)
        sorted_sc, indices = torch.sort(score_1, descending=True)
        idxs = indices[:MAX_KP].numpy()
        resps = score_1[idxs].detach().cpu().numpy()
        kps = coord_1[idxs]
        kps[:, 0] *= coef_w
        kps[:, 1] *= coef_h
        descs = desc1[idxs]
    return kps.detach().cpu().numpy().reshape(-1, 2), resps, descs.detach().cpu().numpy()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--datasets_folder",
        default=os.path.join('..', 'imw-2020'),
        help="path to datasets folder",
        type=str)
    parser.add_argument(
        '--num_kp',
        type=int,
        default=2048,
        help='number of keypoints')
    parser.add_argument(
        '--resize_image_to',
        type=int,
        default=1024,
        help='Resize the largest image dimension to this value (default: 1024, '
        '0 does nothing).')
    parser.add_argument(
        '--device',
        type=str,
        default='cpu',
        choices=["cpu", 'cuda', 'mps']
    )
    parser.add_argument(
        "--save_path",
        default=os.path.join('..', 'benchmark-features'),
        type=str,
        help='Path to store the features')
    parser.add_argument(
        "--method_name", default='superpoint_magicleap', type=str)
    parser.add_argument(
        "--dataset",
        default='all',
        type=str,
        choices=["all", "phototourism", "pragueparks"])
    parser.add_argument(
        "--norm_desc",
        default=False,
        type=str2bool,
        help='L2Norm of descriptors')
    opt, unparsed = parser.parse_known_args()
    device = torch.device(opt.device)
    sp_weights_fname = 'third_party/superpoint_forked/superpoint_v1.pth'
    superpoint = SuperPointFrontend(sp_weights_fname, 4, 0.00015, 0.7, cuda=opt.device=='cuda')
    superpoint.net = superpoint.net.to(device)

    INPUT_DIR = opt.datasets_folder
    modelname = f'{opt.method_name}'
    if opt.norm_desc:
        modelname+='_norm'
    if opt.resize_image_to > 0:
        modelname+= f'_{opt.resize_image_to}'
    else:
        modelname+= f'_fullres'
    OUT_DIR = os.path.join(opt.save_path, modelname)
    os.makedirs(OUT_DIR, exist_ok=True)
    print (f"Will save to {OUT_DIR}")
    if opt.dataset == 'all':
        datasets = [x for x in os.listdir(INPUT_DIR) if (os.path.isdir(os.path.join(INPUT_DIR, x)))]
    else:
        datasets = [opt.dataset]
    for ds in datasets:
        ds_in_path = os.path.join(INPUT_DIR, ds)
        ds_out_path = os.path.join(OUT_DIR, ds)
        os.makedirs(ds_out_path, exist_ok=True)
        seqs = [x for x in os.listdir(ds_in_path) if os.path.isdir(os.path.join(ds_in_path, x))]
        for seq in seqs:
            print (seq)
            if os.path.isdir(os.path.join(ds_in_path, seq, 'set_100')):
                seq_in_path = os.path.join(ds_in_path, seq, 'set_100', 'images')
            else:
                seq_in_path = os.path.join(ds_in_path, seq)
            seq_out_path = os.path.join(ds_out_path, seq)
            os.makedirs(seq_out_path, exist_ok=True)
            img_fnames = os.listdir(seq_in_path)
            num_kp = []
            with h5py.File(f'{seq_out_path}/keypoints.h5', mode='w') as f_kp, \
                 h5py.File(f'{seq_out_path}/descriptors.h5', mode='w') as f_desc, \
                 h5py.File(f'{seq_out_path}/scores.h5', mode='w') as f_score, \
                 h5py.File(f'{seq_out_path}/angles.h5', mode='w') as f_ang, \
                 h5py.File(f'{seq_out_path}/scales.h5', mode='w') as f_scale:
                for img_fname in tqdm(img_fnames):
                    img_fname_full = os.path.join(seq_in_path, img_fname)
                    key = os.path.splitext(os.path.basename(img_fname))[0]
                    kps, resps, descs = extract_features(img_fname_full, superpoint, device,
                                                         opt.num_kp,
                                                         opt.resize_image_to,
                                                         opt.norm_desc)
                    keypoints, scales, angles, responses = convert_imc(kps, resps)
                    f_desc[key] = descs.reshape(-1, 256)
                    f_score[key] = responses
                    f_kp[key] = keypoints
                    f_ang[key] = angles
                    f_scale[key] = scales
                    num_kp.append(len(keypoints))
                print(f'Finished processing "{ds}/{seq}" -> {np.array(num_kp).mean()} features/image')
    print (f"Result is saved to {OUT_DIR}")

