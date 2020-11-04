import torch
import torch.nn as nn
from nn_blocks import *
from torch import optim
import time


class DApredictModel(nn.Module):
    def __init__(self, utt_vocab, da_vocab, config):
        super(DApredictModel, self).__init__()
        if config['DApred']['use_da']:
            self.da_encoder = DAEncoder(da_input_size=len(da_vocab.word2id), da_embed_size=config['DApred']['DA_EMBED'],
                                        da_hidden=config['DApred']['DA_HIDDEN'])
            self.da_context = DAContextEncoder(da_hidden=config['DApred']['DA_HIDDEN'])
        dec_hidden_size = config['DApred']['DA_HIDDEN']+config['DApred']['UTT_CONTEXT']*2+1 if config['DApred']['use_da'] else config['DApred']['UTT_CONTEXT']*2+1
        self.da_decoder = DADecoder(da_input_size=len(da_vocab.word2id), da_embed_size=config['DApred']['DA_EMBED'],
                                    da_hidden=dec_hidden_size)
        self.utt_encoder = UtteranceEncoder(utt_input_size=len(utt_vocab.word2id), embed_size=config['DApred']['UTT_EMBED'],
                                            utterance_hidden=config['DApred']['UTT_HIDDEN'], padding_idx=utt_vocab.word2id['<PAD>'])
        self.utt_context = UtteranceContextEncoder(utterance_hidden_size=config['DApred']['UTT_CONTEXT']*2+1)
        self.attention = Attention(self.utt_encoder.hidden_size*2)
        self.criterion = nn.CrossEntropyLoss(ignore_index=utt_vocab.word2id['<PAD>'])
        self.config = config

    def forward(self, X_da, Y_da, X_utt, turn, step_size):
        """
        X_da:   input sequence of DA, Tensor(window_size, batch_size, 1)
        Y_da:   gold DA, Tensor(batch_size, 1)
        X_utt:  input sentences, Tensor(window_size, batch_size, seq_len, 1)
        turn: whether the next speaker equal to current speaker, Tensor(window_size, batch_size, 1)
        """
        dec_hidden = self._encode(X_da=X_da, X_utt=X_utt, step_size=step_size, turn=turn)
        decoder_output = self.da_decoder(dec_hidden) # (batch_size, 1, DA_VOCAB)
        decoder_output = decoder_output.squeeze(1) # (batch_size, DA_VOCAB)
        Y_da = Y_da.squeeze()
        class_weights = [0, 0.6220204672350252, 0.6349587966404631, 0.8974740205305032, 0.9008272305964602, 0.9811619189219113, 0.9890467076854942, 0.986444806478655, 0.990240893345776, 0.9978251585657119]
        weights = torch.FloatTensor(class_weights).to(device)
        loss = self.criterion(decoder_output, Y_da, weight=weights)
        if self.training:
            loss.backward()
        return loss.item(), decoder_output.data.cpu().numpy()

    def predict(self, X_da, X_utt, turn, step_size):
        with torch.no_grad():
            dec_hidden = self._encode(X_da=X_da, X_utt=X_utt, step_size=step_size, turn=turn)
            decoder_output = self.da_decoder(dec_hidden) # (batch_size, 1, DA_VOCAB)
            decoder_output = decoder_output.squeeze(1) # (batch_size, DA_VOCAB)
            decoder_output = F.softmax(decoder_output, dim=-1)
        return decoder_output.data.cpu().numpy()

    def _encode(self, X_da, X_utt, turn, step_size):
        if self.config['DApred']['use_da']:
            da_context_hidden = self.da_context.initHidden(step_size)
            # da_contexts = []
            for x_da in X_da:
                da_encoder_hidden = self.da_encoder(x_da) # (batch_size, 1, DA_HIDDEN)
                da_context_output, da_context_hidden = self.da_context(da_encoder_hidden, da_context_hidden) # (batch_size, 1, DA_HIDDEN)
                # da_contexts.append(da_context_output)
            # da_context_output = torch.stack(da_contexts).permute(0, 1)
        if self.config['DApred']['use_utt'] and not self.config['DApred']['use_uttcontext']:
            utt_encoder_hidden = self.utt_encoder.initHidden(step_size)
            utt_encoder_output, utt_encoder_hidden = self.utt_encoder(X_utt[-1], utt_encoder_hidden) # (batch_size, 1, UTT_HIDDEN)
            if self.config['DApred']['use_da']:
                dec_hidden = torch.cat((da_context_output, utt_encoder_output), dim=-1)
            else:
                dec_hidden = utt_encoder_output
        elif self.config['DApred']['use_uttcontext']:
            # utt_contexts = []
            utt_context_hidden = self.utt_context.initHidden(step_size)
            for i in range(len(X_utt)):
                utt_encoder_hidden = self.utt_encoder.initHidden(step_size)
                utt_encoder_output, utt_encoder_hidden = self.utt_encoder(X_utt[i], utt_encoder_hidden)  # (batch_size, 1, UTT_HIDDEN)
                # utt_encoder_output = utt_encoder_output.sum(dim=1).unsqueeze(1)
                attns = self.attention(utt_encoder_output)
                utt_encoder_output = (utt_encoder_output * attns).sum(dim=1).unsqueeze(1)
                utt_encoder_output = torch.cat((utt_encoder_output, turn[i].float().unsqueeze(-1)), dim=-1)
                utt_context_output, utt_context_hidden = self.utt_context(utt_encoder_output, utt_context_hidden) # (batch_size, 1, UTT_HIDDEN)
                # utt_contexts.append(utt_context_output)
            # utt_context_output = torch.stack(utt_contexts).permute(0, 1)
            if self.config['DApred']['use_da']:
                dec_hidden = torch.cat((da_context_output, utt_context_output), dim=-1) # (batch_size, 1, DEC_HIDDEN)
                if not self.config['DApred']['use_dacontext']:
                    dec_hidden = torch.cat((da_encoder_hidden, utt_context_output), dim=-1)
            else:
                dec_hidden = utt_context_output
        else:
            dec_hidden = da_context_output
        return dec_hidden
